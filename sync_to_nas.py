# -*- coding: utf-8 -*-
"""SSH 키를 사용하여 로컬 코드를 NAS에 동기화"""

import paramiko
from nas_connection import connect_nas
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def sync_to_nas():
    """SSH 키를 사용하여 로컬 Python 파일들을 NAS에 동기화"""

    ssh = paramiko.SSHClient()

    try:
        # SSH 키 경로
        from pathlib import Path
        key_path = Path.home() / ".ssh" / "id_rebalancer"

        # 프로젝트 .secrets 폴더도 확인
        project_key = Path(__file__).parent / ".secrets" / "id_rebalancer"

        if not key_path.exists() and project_key.exists():
            key_path = project_key

        logger.info(f"Loading SSH key from: {key_path}")

        if not key_path.exists():
            logger.error(f"SSH key not found at {key_path}")
            raise FileNotFoundError(f"SSH key not found at {key_path}")

        private_key = paramiko.RSAKey.from_private_key_file(str(key_path))
        logger.info("SSH key loaded successfully")

        logger.info("Connecting to NAS with SSH key...")
        ssh.connect(
            hostname='192.168.0.46',
            username='doogie_admin',
            pkey=private_key,
            port=22,
            timeout=30
        )
        logger.info("✅ Connected to NAS using SSH key")

        # SFTP 클라이언트 생성
        sftp = ssh.open_sftp()
        logger.info("SFTP channel opened")

        # 동기화할 Python 파일 목록
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
            "webhook_notifier.py",
            "performance_report_engine.py",
            "signal_accuracy_engine.py",
            "scheduler.py",
            "main.py",
        ]

        logger.info(f"\n{'='*80}")
        logger.info(f"Syncing Python files to NAS ({nas_dir})...")
        logger.info('='*80)

        synced_files = 0
        for filename in python_files:
            local_path = local_dir / filename
            nas_path = f"{nas_dir}/{filename}"

            if not local_path.exists():
                logger.warning(f"⚠️  Local file not found: {local_path}")
                continue

            try:
                logger.info(f"Syncing: {filename}")
                sftp.put(str(local_path), nas_path)
                synced_files += 1
                logger.info(f"  ✅ {filename}")
            except Exception as e:
                logger.error(f"  ❌ Failed to sync {filename}: {e}")

        logger.info(f"\n{'='*80}")
        logger.info(f"Synced {synced_files}/{len(python_files)} files successfully")
        logger.info('='*80)

        # 동기화 후 NAS의 파일 확인
        logger.info("\nVerifying files on NAS...")
        stdin, stdout, stderr = ssh.exec_command(f"ls -la {nas_dir}/*.py | wc -l")
        output = stdout.read().decode('utf-8').strip()
        logger.info(f"Python files on NAS: {output} files")

        # 동기화 후 NAS에서 API 서버 재시작
        logger.info("\n" + "="*80)
        logger.info("Restarting API server on NAS...")
        logger.info("="*80)

        restart_cmd = "sudo systemctl restart rebalancer"
        stdin, stdout, stderr = ssh.exec_command(restart_cmd)

        time.sleep(2)

        # 서비스 상태 확인
        logger.info("Checking service status...")
        status_cmd = "sudo systemctl status rebalancer | head -10"
        stdin, stdout, stderr = ssh.exec_command(status_cmd)
        output = stdout.read().decode('utf-8')

        logger.info("Service status:")
        for line in output.split('\n')[:5]:
            if line.strip():
                logger.info(f"  {line}")

        # Health check
        logger.info("\nPerforming health check...")
        health_cmd = "curl -s http://localhost:8000/health | python3 -m json.tool"
        stdin, stdout, stderr = ssh.exec_command(health_cmd)
        output = stdout.read().decode('utf-8')

        logger.info("Health check result:")
        if output:
            logger.info(output)
        else:
            logger.warning("Health check returned empty result")

        sftp.close()
        logger.info("\n✅ Sync and restart completed successfully!")

    except paramiko.ssh_exception.SSHException as e:
        logger.error(f"SSH Error: {e}")
        logger.info("Trying with password authentication...")
        # 패스워드로 재시도
        connect_nas(ssh, timeout=30)
        logger.info("Connected with password")
        sync_to_nas()  # 재귀 호출
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            ssh.close()
        except:
            pass

if __name__ == "__main__":
    import time
    sync_to_nas()
