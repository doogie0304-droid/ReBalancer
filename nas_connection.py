# -*- coding: utf-8 -*-
"""NAS SSH 접속 헬퍼

접속정보(호스트/계정/비밀번호/키 경로)는 코드에 적지 않고 .env.local에서만 읽는다.
.env.local은 .gitignore에 등록되어 있어 저장소에 올라가지 않는다.
"""

import os
from pathlib import Path

import paramiko
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env.local", override=True, encoding="utf-8-sig")

NAS_HOST = os.getenv("NAS_IP", "")
NAS_SSH_PORT = int(os.getenv("NAS_SSH_PORT", "22"))
NAS_SSH_USER = os.getenv("NAS_SSH_USER", "")
NAS_SSH_PASS = os.getenv("NAS_SSH_PASS", "")
NAS_SSH_KEY = os.getenv("NAS_SSH_KEY", "~/.ssh/id_rebalancer")
NAS_PROJECT_DIR = os.getenv("NAS_PROJECT_DIR", "/volume1/rebalancer")


def connect_nas(ssh: paramiko.SSHClient = None, timeout: int = 10) -> paramiko.SSHClient:
    """NAS에 SSH 접속한다. 키 파일이 있으면 키 인증, 없으면 .env.local의 비밀번호를 쓴다.

    호스트 키는 ~/.ssh/known_hosts에 등록된 것만 허용한다(미등록 호스트는 거부).
    """
    if not NAS_HOST or not NAS_SSH_USER:
        raise RuntimeError(".env.local에 NAS_IP / NAS_SSH_USER가 없습니다.")

    if ssh is None:
        ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    kwargs = {
        "hostname": NAS_HOST,
        "port": NAS_SSH_PORT,
        "username": NAS_SSH_USER,
        "timeout": timeout,
        "allow_agent": False,
        "look_for_keys": False,
    }
    key_path = Path(os.path.expanduser(NAS_SSH_KEY)) if NAS_SSH_KEY else None
    if key_path and key_path.exists():
        kwargs["key_filename"] = str(key_path)
    if NAS_SSH_PASS:
        kwargs["password"] = NAS_SSH_PASS
    if "key_filename" not in kwargs and "password" not in kwargs:
        raise RuntimeError(".env.local에 NAS_SSH_KEY(키 파일) 또는 NAS_SSH_PASS가 필요합니다.")

    ssh.connect(**kwargs)
    return ssh
