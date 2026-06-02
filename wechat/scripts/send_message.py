from __future__ import annotations

import json
from pathlib import Path

from common import prepare_pyweixin


def main():
    root = Path(r"C:\Users\j1383\Desktop\data_AI\my_agent\wechat")

    pyweixin = prepare_pyweixin(str(root))

    pyweixin.Messages.send_messages_to_friend(
        friend="林峰",
        messages=["色即是空"],
        close_weixin=False,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "friend": "林峰",
                "message": "色即是空",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()