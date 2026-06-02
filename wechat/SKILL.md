---
name: wechat-contact-assistant
description: Send a text message or one or more local files to one specific desktop WeChat contact on Windows by driving a locally installed pywechat/pyweixin environment. Use when OpenClaw needs to message a single WeChat contact or deliver local files through the logged-in desktop WeChat client.
---

# Wechat Contact Assistant

## Overview

Use this skill to bridge OpenClaw with a local Windows WeChat client. The skill does not call any external LLM API. Its job is to send text messages and local files to one contact through desktop WeChat.

## Prerequisites

- Ensure Windows desktop WeChat is already installed and logged in.
- Ensure the local `pywechat` repository and its dependencies are already working.
- Set `PYWECHAT_ROOT` to the local repo root when possible. Example: `C:\Users\j1383\Desktop\chat\pywechat`
- Keep WeChat window automation prerequisites satisfied for version 4.1+.
If UI discovery is unstable, use the same Narrator-before-login setup that makes `pyweixin` work on this machine.

## Workflow

1. Choose the target contact by remark or display name.
2. Send one text message with `scripts/send_message.py`, or send one or more local files with `scripts/send_file.py`.
3. Read the JSON success payload and continue with the next explicit send if needed.

## Scripts

### Send a message

Run:

```powershell
python scripts/send_message.py --friend "Contact Name" --message "Hello from OpenClaw" --pywechat-root "C:\path\to\pywechat"
```

Behavior:

- Open the contact chat.
- Send exactly one text message.
- Return a short JSON success payload.

### Send file(s)

Run:

```powershell
python scripts/send_file.py --friend "Contact Name" --file "C:\path\to\file.pdf" --pywechat-root "C:\path\to\pywechat"
```

You can repeat `--file` to send multiple files, or pass a folder path to send every file inside that folder.

Behavior:

- Open the contact chat.
- Send one or more local files.
- Optionally send text together with the files by repeating `--message`.
- Use `--messages-first` if text should be sent before the file upload.
- Return a short JSON success payload with the resolved file paths.

## Operating Rules

- This skill is send-only. It does not listen for or read incoming messages.
- File sending is supported, but reading voice, images, chat history, or file contents from the chat window is not.
- If the user asks to inspect incoming WeChat content, state that the current skill only supports sending text and local files.
- Prefer explicit sends instead of background automation.
