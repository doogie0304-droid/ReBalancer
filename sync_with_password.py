# -*- coding: utf-8 -*-
"""패스워드 기반 SSH로 로컬 코드를 NAS에 동기화"""

import paramiko
from nas_connection import connect_nas
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def sync_files():
    ssh = paramiko.SSHClient()

    try:
        logger.info("=" * 80)
        logger.info("NAS Code Sync (Password-based)")
        logger.info("=" * 80)

        # SSH 연결
        logger.info("Connecting to NAS...")
        connect_nas(ssh, timeout=30)
        logger.info("✅ Connected to NAS")

        # SFTP 채널
        try:
            sftp = ssh.open_sftp()
            logger.info("✅ SFTP channel opened")

            local_dir = Path(r"C:\My_Obsidian\Projects\ReBalancer")
            nas_dir = "/volume1/rebalancer"

            python_files = [
                "config.py",
                "database.py",
                "crawler.py",
                "momentum_engine.py",
                "rebalance_engine.py",
                "portfolio_engine.py",
                "notification.py",
                "signal_accuracy_engine.py",
                "scheduler.py",
                "main.py",
            ]

            logger.info(f"\nSyncing {len(python_files)} Python files...")
            logger.info("-" * 80)

            synced = 0
            for filename in python_files:
                local_path = local_dir / filename
                nas_path = f"{nas_dir}/{filename}"

                if not local_path.exists():
                    logger.warning(f"⚠️  {filename} - NOT FOUND")
                    continue

                try:
                    logger.info(f"Syncing: {filename}... ", end="")
                    sftp.put(str(local_path), nas_path)
                    logger.info("✅")
                    synced += 1
                except Exception as e:
                    logger.error(f"❌ Error: {e}")

            logger.info("-" * 80)
            logger.info(f"\n✅ Synced {synced}/{len(python_files)} files")

            sftp.close()

        except Exception as e:
            logger.warning(f"SFTP not available, using SSH shell: {e}")
            # SFTP 실패시 SSH 쉘 명령어 사용
            sync_with_shell(ssh)
            return

        # API 서버 재시작
        logger.info("\n" + "=" * 80)
        logger.info("Restarting API server...")
        logger.info("=" * 80)

        stdin, stdout, stderr = ssh.exec_command("sudo systemctl restart rebalancer")
        time.sleep(3)

        # 서비스 상태 확인
        logger.info("\nService status:")
        stdin, stdout, stderr = ssh.exec_command("sudo systemctl status rebalancer | head -5")
        output = stdout.read().decode('utf-8', errors='ignore')
        for line in output.split('\n'):
            if line.strip():
                logger.info(f"  {line}")

        # Health check
        logger.info("\nHealth check:")
        stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8000/health")
        output = stdout.read().decode('utf-8', errors='ignore')
        if "healthy" in output:
            logger.info(f"  ✅ {output}")
        else:
            logger.info(f"  {output}")

        logger.info("\n" + "=" * 80)
        logger.info("✅ Sync and restart completed!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

def sync_with_shell(ssh):
    """SSH shell을 사용한 동기화"""
    logger.info("\nUsing SSH shell for file sync...")

    python_files = [
        "config.py", "database.py", "crawler.py", "momentum_engine.py",
        "rebalance_engine.py", "portfolio_engine.py", "notification.py",
        "signal_accuracy_engine.py", "scheduler.py", "main.py"
    ]

    synced = 0
    for filename in python_files:
        local_path = Path(r"C:\My_Obsidian\Projects\ReBalancer") / filename

        if not local_path.exists():
            logger.warning(f"⚠️  {filename} - NOT FOUND")
            continue

        # Windows 경로를 Unix 경로로 변환
        unix_local_path = str(local_path).replace("\\", "/")

        logger.info(f"Syncing: {filename}... ", end="")

        # dd를 사용한 파일 복사
        read_cmd = f"cat < '{unix_local_path}' | ssh doogie_admin@192.168.0.46 'cat > /volume1/rebalancer/{filename}'"

        try:
            # Shell 실행
            import subprocess
            result = subprocess.run(read_cmd, shell=True, capture_output=True, timeout=30)

            if result.returncode == 0:
                logger.info("✅")
                synced += 1
            else:
                logger.error(f"❌ Exit code: {result.returncode}")

        except Exception as e:
            logger.error(f"❌ Error: {e}")

    logger.info(f"\n✅ Synced {synced}/{len(python_files)} files")

if __name__ == "__main__":
    sync_files()
