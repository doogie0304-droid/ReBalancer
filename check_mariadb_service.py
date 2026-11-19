# -*- coding: utf-8 -*-
"""NAS MariaDB 서비스 상태 확인"""

import paramiko
from nas_connection import connect_nas
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_nas_service():
    ssh = paramiko.SSHClient()

    try:
        logger.info("NAS 접속 중...")
        connect_nas(ssh, timeout=10)
        logger.info("NAS 접속 성공")

        # MariaDB 서비스 상태 확인
        commands = [
            ("MariaDB 서비스 상태", "sudo /usr/syno/bin/synoservice --status mysql"),
            ("MariaDB 프로세스", "ps aux | grep mysql"),
            ("포트 확인", "netstat -tlnp | grep 3306"),
            ("데이터 폴더", "ls -la /volume1/rebalancer/"),
            ("Python 버전", "python3 --version")
        ]

        for desc, cmd in commands:
            logger.info(f"\n{desc}:")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            output = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')

            print(f"[{desc}]")
            if output:
                print(output)
            if error and "command not found" not in error:
                print(f"Error: {error}")

    finally:
        ssh.close()

if __name__ == "__main__":
    check_nas_service()
