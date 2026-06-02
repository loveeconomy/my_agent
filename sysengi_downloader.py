#!/usr/bin/env python3
"""
系统工程理论与实践 论文下载器
从 sysengi.cjoe.ac.cn 下载论文 PDF
"""

import os
import re
import sys
import json
import time
import argparse
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("请先安装 requests: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sysengi_download.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE_URL = "https://sysengi.cjoe.ac.cn"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


def decode_response(resp):
    """正确解码响应内容（网站使用GBK编码）"""
    # 尝试常见中文编码
    for enc in ('gb18030', 'gbk', 'gb2312', 'utf-8'):
        try:
            return resp.content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return resp.content.decode('gb18030', errors='replace')


class SysengiDownloader:
    """系统工程理论与实践 论文下载器"""

    def __init__(self, output_dir: str = "./sysengi_papers"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.stats = {'success': 0, 'failed': 0, 'skipped': 0}
        self.downloaded_file = self.output_dir / "downloaded.json"
        self.downloaded_papers = self._load_downloaded()

    def _load_downloaded(self) -> set:
        if self.downloaded_file.exists():
            try:
                with open(self.downloaded_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

    def _save_downloaded(self):
        with open(self.downloaded_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.downloaded_papers), f, ensure_ascii=False, indent=2)

    def _sanitize_filename(self, filename: str) -> str:
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        if len(filename) > 200:
            filename = filename[:200]
        return filename.strip()

    def _is_valid_pdf(self, file_path: Path) -> bool:
        try:
            with open(file_path, 'rb') as f:
                return f.read(5) == b'%PDF-'
        except Exception:
            return False

    def _get_paper_hash(self, doi: str) -> str:
        return hashlib.md5(doi.lower().strip().encode()).hexdigest()

    def _clean_cookies(self):
        """清理所有cookie，重新开始"""
        self.session.cookies.clear()

    # ==================== 获取期刊目录 ====================

    def get_all_issues(self) -> List[Dict]:
        """获取所有过刊列表"""
        url = f"{BASE_URL}/CN/article/showOldVolumn.do"
        logger.info("获取过刊列表...")
        try:
            resp = self.session.get(url, timeout=30)
            html = decode_response(resp)
            # 解析: /CN/Y2026/V46/I4 格式的链接
            pattern = r'/CN/Y(\d{4})/V(\d+)/I(\d+)'
            matches = re.findall(pattern, html)
            # 去重并排序
            issues = []
            seen = set()
            for year, vol, issue in matches:
                key = f"{year}-{vol}-{issue}"
                if key not in seen:
                    seen.add(key)
                    issues.append({
                        'year': int(year),
                        'vol': int(vol),
                        'issue': int(issue),
                        'url': f"{BASE_URL}/CN/Y{year}/V{vol}/I{issue}"
                    })
            issues.sort(key=lambda x: (x['year'], x['vol'], x['issue']), reverse=True)
            logger.info(f"共找到 {len(issues)} 期")
            return issues
        except Exception as e:
            logger.error(f"获取过刊列表失败: {e}")
            return []

    def get_issue_articles(self, year: int, vol: int, issue: int) -> List[Dict]:
        """获取指定期的所有论文列表"""
        url = f"{BASE_URL}/CN/Y{year}/V{vol}/I{issue}"
        logger.info(f"获取目录: {year}年第{vol}卷第{issue}期")
        try:
            resp = self.session.get(url, timeout=30)
            html = decode_response(resp)
            return self._parse_article_list(html)
        except Exception as e:
            logger.error(f"获取目录失败: {e}")
            return []

    def _parse_article_list(self, html: str) -> List[Dict]:
        """解析HTML中的论文列表（适用于目录页和搜索结果页）"""
        articles = []

        # 查找所有文章块: value="{id}" ... name=pid (搜索结果)
        # 或 class="article_checkbox" ... value="{id}" (目录页)
        # 统一用灵活的方式提取

        # 方式1: 通过 name=pid 定位文章checkbox（兼容单引号和双引号）
        pid_blocks = re.findall(
            r"""value=['"](\d+)['"]\s+alt=\w+\s+type=checkbox\s+name=pid>.*?"""
            r'<div class="j-title-1">\s*(?:<!--.*?-->)?\s*'
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?'
            r'<div class="j-author">(.*?)</div>',
            html, re.DOTALL
        )

        for article_id, href, title, authors_html in pid_blocks:
            if not article_id.isdigit():
                continue
            title = title.strip()
            if not title or title == '封面目录':
                continue
            # 从href提取doi_path
            doi_path_match = re.search(r'/CN/(.+)$', href)
            if not doi_path_match:
                continue
            doi_path = doi_path_match.group(1)
            doi_match = re.search(r'10\.\d+/.+', doi_path)
            doi = doi_match.group(0) if doi_match else doi_path
            authors = re.sub(r'<[^>]+>', '', authors_html).strip()
            authors = re.sub(r'\s+', ' ', authors)

            articles.append({
                'article_id': article_id,
                'doi': doi,
                'doi_path': doi_path,
                'title': title,
                'authors': authors,
                'detail_url': f"{BASE_URL}/CN/{doi_path}",
            })

        if articles:
            return articles

        # 方式2: 通过 class="article_checkbox" 定位（兼容单引号和双引号）
        checkbox_blocks = re.findall(
            r"""<input[^>]*class=['"]article_checkbox['"][^>]*value=['"](\d+)['"][^>]*>.*?"""
            r'<div class="j-title-1">\s*(?:<!--.*?-->)?\s*'
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?'
            r'<div class="j-author"[^>]*>(.*?)</div>',
            html, re.DOTALL
        )

        for article_id, href, title, authors_html in checkbox_blocks:
            if not article_id.isdigit():
                continue
            title = title.strip()
            if not title or title == '封面目录':
                continue
            doi_path_match = re.search(r'/CN/(.+)$', href)
            if not doi_path_match:
                continue
            doi_path = doi_path_match.group(1)
            doi_match = re.search(r'10\.\d+/.+', doi_path)
            doi = doi_match.group(0) if doi_match else doi_path
            authors = re.sub(r'<[^>]+>', '', authors_html).strip()
            authors = re.sub(r'\s+', ' ', authors)

            articles.append({
                'article_id': article_id,
                'doi': doi,
                'doi_path': doi_path,
                'title': title,
                'authors': authors,
                'detail_url': f"{BASE_URL}/CN/{doi_path}",
            })

        if articles:
            return articles

        # 方式3: 最宽松的匹配 - 找所有 j-title-1 中的链接
        logger.debug("使用宽松模式解析文章列表...")
        title_links = re.findall(
            r'<div class="j-title-1">\s*(?:<!--.*?-->)?\s*'
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
            html, re.DOTALL
        )
        author_divs = re.findall(
            r'<div class="j-author">(.*?)</div>',
            html, re.DOTALL
        )
        # 找所有 name=pid 的 id（兼容单引号和双引号）
        pid_ids = re.findall(r"""value=['"](\d+)['"]\s+alt=\w+\s+type=checkbox\s+name=pid>""", html)
        # 找所有 article_checkbox 的 id（兼容单引号和双引号）
        cb_ids = re.findall(r"""class=['"]article_checkbox['"][^>]*value=['"](\d+)['"]""", html)
        all_ids = pid_ids or cb_ids

        logger.debug(f"宽松模式: ids={len(all_ids)}, titles={len(title_links)}, authors={len(author_divs)}")

        for i, (href, title) in enumerate(title_links):
            title = title.strip()
            if not title or title in ('封面目录', ''):
                continue
            doi_path_match = re.search(r'/CN/(.+)$', href)
            if not doi_path_match:
                continue
            doi_path = doi_path_match.group(1)
            # 跳过导航链接
            if doi_path in ('home',) or doi_path.startswith('column'):
                continue
            doi_match = re.search(r'10\.\d+/.+', doi_path)
            doi = doi_match.group(0) if doi_match else doi_path
            article_id = all_ids[i] if i < len(all_ids) else ''
            authors = ''
            if i < len(author_divs):
                authors = re.sub(r'<[^>]+>', '', author_divs[i]).strip()
                authors = re.sub(r'\s+', ' ', authors)

            articles.append({
                'article_id': article_id,
                'doi': doi,
                'doi_path': doi_path,
                'title': title,
                'authors': authors,
                'detail_url': f"{BASE_URL}/CN/{doi_path}",
            })

        return articles

    # ==================== 搜索论文 ====================

    def search_by_title(self, title: str) -> List[Dict]:
        """通过网站搜索功能按标题搜索论文"""
        logger.info(f"搜索论文: {title}")
        search_url = f"{BASE_URL}/CN/article/advancedSearchResult.do"
        search_sql = f"({title}[Title])"
        data = {'searchSQL': search_sql}
        try:
            self._clean_cookies()
            resp = self.session.post(search_url, data=data, timeout=60)
            html = decode_response(resp)
            logger.debug(f"搜索响应: status={resp.status_code}, length={len(html)}")
            results = self._parse_article_list(html)
            # 过滤: 只保留标题相关的（搜索结果可能包含无关项）
            if results:
                title_lower = title.lower()
                filtered = [r for r in results if title_lower in r['title'].lower()]
                if filtered:
                    results = filtered
            return results
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    # ==================== 下载PDF ====================

    def get_pdf_url(self, article_id: str, doi_path: str) -> Optional[str]:
        """通过API获取PDF下载链接"""
        if not article_id:
            return None
        detail_url = f"{BASE_URL}/CN/{doi_path}"
        api_url = f"{BASE_URL}/CN/article/showArticleFile.do"
        data = f"attachType=PDF&id={article_id}&json=true"
        headers = {
            'Referer': detail_url,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        for attempt in range(3):
            try:
                self._clean_cookies()
                if attempt > 0:
                    self.session.get(detail_url, timeout=30)

                resp = self.session.post(api_url, data=data, headers=headers, timeout=30)
                text = resp.text.strip()

                if text.startswith('[json]'):
                    info = json.loads(text[6:])
                    if info.get('status') == 1 and info.get('pdfUrl'):
                        return info['pdfUrl']
                    elif info.get('status') == 4:
                        logger.warning(f"论文需要付费: {doi_path}")
                        return None
                time.sleep(1)
            except Exception as e:
                logger.debug(f"获取PDF链接失败 (尝试 {attempt+1}): {e}")
                time.sleep(1)

        return None

    def download_paper(self, paper: Dict) -> Tuple[bool, str]:
        """下载单篇论文"""
        doi = paper.get('doi', '')
        title = paper.get('title', '')
        article_id = paper.get('article_id', '')

        if not doi:
            return False, "缺少DOI信息"

        # 检查是否已下载
        paper_hash = self._get_paper_hash(doi)
        if paper_hash in self.downloaded_papers:
            logger.info(f"已下载，跳过: {title}")
            self.stats['skipped'] += 1
            return True, "已下载"

        # 生成文件名: 作者 - 标题.pdf
        authors = paper.get('authors', '')
        first_author = authors.split(',')[0].split('，')[0].strip() if authors else ''
        if first_author and title:
            filename = f"{first_author} - {title}"
        else:
            filename = title or doi.replace('/', '_')
        filename = self._sanitize_filename(filename)
        if not filename.endswith('.pdf'):
            filename += '.pdf'

        save_path = self.output_dir / filename
        if save_path.exists():
            self.downloaded_papers.add(paper_hash)
            self._save_downloaded()
            self.stats['skipped'] += 1
            return True, "文件已存在"

        # 获取PDF链接
        pdf_url = self.get_pdf_url(article_id, paper.get('doi_path', doi))
        if not pdf_url:
            self.stats['failed'] += 1
            return False, "获取PDF链接失败"

        # 下载PDF
        try:
            resp = self.session.get(pdf_url, timeout=60, stream=True)
            resp.raise_for_status()

            with open(save_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if self._is_valid_pdf(save_path):
                self.downloaded_papers.add(paper_hash)
                self._save_downloaded()
                self.stats['success'] += 1
                logger.info(f"下载成功: {filename}")
                return True, "下载成功"
            else:
                save_path.unlink(missing_ok=True)
                self.stats['failed'] += 1
                return False, "文件验证失败(非有效PDF)"
        except Exception as e:
            save_path.unlink(missing_ok=True)
            self.stats['failed'] += 1
            return False, f"下载失败: {e}"

    # ==================== 批量下载 ====================

    def download_by_title(self, title: str) -> Dict:
        """按标题搜索并下载"""
        papers = self.search_by_title(title)
        if not papers:
            logger.warning(f"未找到标题包含 '{title}' 的论文")
            return self.stats

        logger.info(f"找到 {len(papers)} 篇匹配论文:")
        for i, p in enumerate(papers, 1):
            logger.info(f"  {i}. {p['title']} ({p['authors']})")

        for i, paper in enumerate(papers, 1):
            logger.info(f"[{i}/{len(papers)}] 下载: {paper['title']}")
            success, msg = self.download_paper(paper)
            if not success:
                logger.warning(f"  失败: {msg}")
            time.sleep(1)

        self._print_stats()
        return self.stats

    def download_issue(self, year: int, vol: int, issue: int) -> Dict:
        """下载整期论文"""
        articles = self.get_issue_articles(year, vol, issue)
        if not articles:
            logger.warning(f"未找到 {year}年{vol}卷{issue}期的论文")
            return self.stats

        logger.info(f"共 {len(articles)} 篇论文")
        for i, paper in enumerate(articles, 1):
            logger.info(f"[{i}/{len(articles)}] {paper['title']}")
            success, msg = self.download_paper(paper)
            if not success:
                logger.warning(f"  失败: {msg}")
            time.sleep(1)

        self._print_stats()
        return self.stats

    def download_year(self, year: int) -> Dict:
        """下载某一年所有论文"""
        issues = self.get_all_issues()
        year_issues = [i for i in issues if i['year'] == year]
        if not year_issues:
            logger.warning(f"未找到 {year} 年的期刊")
            return self.stats

        logger.info(f"{year} 年共 {len(year_issues)} 期")
        for issue_info in year_issues:
            logger.info(f"\n{'='*50}")
            logger.info(f"处理: {year}年 第{issue_info['vol']}卷 第{issue_info['issue']}期")
            self.download_issue(issue_info['year'], issue_info['vol'], issue_info['issue'])

        self._print_stats()
        return self.stats

    def download_all(self) -> Dict:
        """下载所有过刊"""
        issues = self.get_all_issues()
        if not issues:
            logger.warning("未找到任何期刊")
            return self.stats

        logger.info(f"共 {len(issues)} 期待下载")
        for issue_info in issues:
            logger.info(f"\n{'='*50}")
            logger.info(f"处理: {issue_info['year']}年 第{issue_info['vol']}卷 第{issue_info['issue']}期")
            self.download_issue(issue_info['year'], issue_info['vol'], issue_info['issue'])

        self._print_stats()
        return self.stats

    def _print_stats(self):
        logger.info(f"\n{'='*50}")
        logger.info(f"下载完成! 成功: {self.stats['success']}, "
                     f"失败: {self.stats['failed']}, 跳过: {self.stats['skipped']}")


def main():
    parser = argparse.ArgumentParser(
        description='系统工程理论与实践 论文下载器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 按标题搜索下载
  python sysengi_downloader.py --title "国际大宗商品资产行业配置研究"

  # 下载指定期
  python sysengi_downloader.py --year 2014 --vol 34 --issue 5

  # 下载某年所有期
  python sysengi_downloader.py --year 2014

  # 下载所有过刊
  python sysengi_downloader.py --all

  # 指定输出目录
  python sysengi_downloader.py --title "大宗商品" --output ./papers
        """
    )

    parser.add_argument('--title', '-t', type=str, help='论文标题（搜索下载）')
    parser.add_argument('--year', '-y', type=int, help='年份')
    parser.add_argument('--vol', '-v', type=int, help='卷号')
    parser.add_argument('--issue', '-i', type=int, help='期号')
    parser.add_argument('--all', action='store_true', help='下载所有过刊')
    parser.add_argument('--output', '-o', type=str, default='./sysengi_papers', help='输出目录')
    parser.add_argument('--delay', type=float, default=1.0, help='下载间隔(秒)')

    args = parser.parse_args()

    downloader = SysengiDownloader(output_dir=args.output)

    if args.title:
        downloader.download_by_title(args.title)
    elif args.all:
        downloader.download_all()
    elif args.year and args.vol and args.issue:
        downloader.download_issue(args.year, args.vol, args.issue)
    elif args.year:
        downloader.download_year(args.year)
    else:
        # 默认进入交互模式
        print("=" * 60)
        print("  系统工程理论与实践 论文下载器")
        print("=" * 60)

        while True:
            print("\n请选择操作:")
            print("  1. 按标题搜索下载")
            print("  2. 按期下载")
            print("  3. 按年下载")
            print("  4. 下载所有过刊")
            print("  5. 退出")

            choice = input("\n请输入选择 (1-5): ").strip()

            if choice == '1':
                title = input("请输入论文标题: ").strip()
                if title:
                    downloader.download_by_title(title)

            elif choice == '2':
                year = input("请输入年份: ").strip()
                vol = input("请输入卷号: ").strip()
                issue = input("请输入期号: ").strip()
                try:
                    downloader.download_issue(int(year), int(vol), int(issue))
                except ValueError:
                    print("输入格式错误")

            elif choice == '3':
                year = input("请输入年份: ").strip()
                try:
                    downloader.download_year(int(year))
                except ValueError:
                    print("输入格式错误")

            elif choice == '4':
                confirm = input("确认下载所有过刊？(y/n): ").strip().lower()
                if confirm == 'y':
                    downloader.download_all()

            elif choice == '5':
                print("退出程序")
                break

            else:
                print("无效选择")


if __name__ == '__main__':
    main()
