from __future__ import annotations

import argparse
import json

from common import prepare_pyweixin, resolve_files_to_send


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one or more files to a WeChat contact.")
    parser.add_argument("--friend", required=True, help="Contact remark or display name.")
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        required=True,
        help="File path to send. Repeat the flag for multiple files, or pass a folder path.",
    )
    parser.add_argument(
        "--message",
        action="append",
        default=[],
        help="Optional text message to send together with the file(s). Repeat the flag for multiple messages.",
    )
    parser.add_argument(
        "--messages-first",
        action="store_true",
        help="Send --message content before sending the file(s).",
    )
    parser.add_argument("--pywechat-root", help="Path to the local pywechat repository root.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pyweixin = prepare_pyweixin(args.pywechat_root)
    files = resolve_files_to_send(args.files)
    messages = [message for message in args.message if message]

    pyweixin.Files.send_files_to_friend(
        friend=args.friend,
        files=files,
        with_messages=bool(messages),
        messages=messages,
        messages_first=args.messages_first,
        close_weixin=False,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "friend": args.friend,
                "files": files,
                "messages": messages,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
