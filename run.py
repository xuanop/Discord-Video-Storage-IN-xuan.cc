import os
import stat
import urllib.request
import tarfile
from keep_alive import keep_alive
import bot

def ensure_linux_ffmpeg():
    target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg.exe')
    if os.name != 'nt' and not os.path.exists(target_path):
        print("⏳ 检测到云端 Linux 环境缺少 ffmpeg，正在自动下载静态编译版...")
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        tar_path = "ffmpeg.tar.xz"
        try:
            urllib.request.urlretrieve(url, tar_path)
            with tarfile.open(tar_path, "r:xz") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("ffmpeg"):
                        extracted_file = tar.extractfile(member)
                        with open(target_path, "wb") as f_out:
                            f_out.write(extracted_file.read())
                        break
            os.remove(tar_path)
            os.chmod(target_path, stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print("✅ 智能云端 FFmpeg 挂载成功！")
        except Exception as e:
            print(f"⚠️ 自动下载 FFmpeg 失败: {e}")

if __name__ == "__main__":
    ensure_linux_ffmpeg()
    keep_alive()
    print("🌐 云端保活与服务已启动...")