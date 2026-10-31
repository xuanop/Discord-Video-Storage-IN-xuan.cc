import os
import subprocess
import re
import asyncio
import json
import time
import requests
import urllib.parse
import urllib.request
import threading
import sys
import logging
from collections import deque
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import importlib.metadata

from dotenv import load_dotenv
load_dotenv(".env")

def mask_token(token):
    if not token or len(token) < 10:
        return "None / 格式错误"
    return f"{token[:4]}****{token[-4:]}"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

print(f"DEBUG - 读取到的 DISCORD_TOKEN: {mask_token(DISCORD_TOKEN)}")
print(f"DEBUG - 读取到的 GITHUB_TOKEN: {mask_token(GITHUB_TOKEN)}")

try:
    ytdlp_version = importlib.metadata.version("yt-dlp")
except Exception:
    ytdlp_version = "Unknown"
print(f"DEBUG - 当前核心组件 yt-dlp 版本: {ytdlp_version} (核心组件常新监测已激活)")

if not DISCORD_TOKEN:
    print("❌ 错误：未检测到 DISCORD_TOKEN 环境变量！")

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

URL_REGEX = re.compile(r'https?://[^\s]+')

GITHUB_USER = "xuanop"
GITHUB_REPO = "Discord-Video-Storage-IN-xuan.cc"
TAG_NAME = "v1.0.0"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(CURRENT_DIR, 'ffmpeg.exe')
STATS_FILE = os.path.join(CURRENT_DIR, 'download_stats.txt')

BRIDGE_STATUS_FILE = os.path.join(CURRENT_DIR, 'bot_bridge_status.json')
COMMAND_FILE = os.path.join(CURRENT_DIR, 'bot_bridge_command.json')

BOT_SETTINGS = {
    "allow_bilibili": True,
    "allow_youtube": True,
    "allow_tiktok": True,
    "auto_upload": True
}

def load_stats():
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "total_downloaded_mb": float(data.get("total_downloaded_mb", 0.0)),
                    "download_count": int(data.get("download_count", 0))
                }
    except Exception as e:
        print(f"⚠️ 读取下载统计档案失败: {e}")
    return {"total_downloaded_mb": 0.0, "download_count": 0}

def save_stats():
    try:
        data = {
            "total_downloaded_mb": TASK_STATUS["total_downloaded_mb"],
            "download_count": TASK_STATUS["download_count"]
        }
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ 储存下载统计档案失败: {e}")

initial_stats = load_stats()

TASK_STATUS = {
    "status": "idle",
    "progress": 0,
    "message": "系统闲置中，等待下载任务...",
    "total_downloaded_mb": initial_stats["total_downloaded_mb"],
    "download_count": initial_stats["download_count"]
}

DISABLED_GUILDS = set()
LOG_BUFFER = deque(maxlen=200)

class StdoutRedirector:
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, str_val):
        self.original_stream.write(str_val)
        cleaned = str_val.strip()
        if cleaned:
            LOG_BUFFER.append(str_val)

    def flush(self):
        self.original_stream.flush()

sys.stdout = StdoutRedirector(sys.stdout)
sys.stderr = StdoutRedirector(sys.stderr)

@bot.event
async def on_ready():
    print(f"✨ 官方影音下载机器人已上线：{bot.user}")

@bot.event
async def on_guild_join(guild):
    print(f"➕ 机器人已加入新服务器: {guild.name} (ID: {guild.id})")

@bot.event
async def on_guild_remove(guild):
    print(f"➖ 机器人已离开服务器: {guild.name} (ID: {guild.id})")
    if guild.id in DISABLED_GUILDS:
        DISABLED_GUILDS.remove(guild.id)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild and message.guild.id in DISABLED_GUILDS:
        return

    content = message.content
    trigger_pattern = re.compile(r'(https?://(?:[^\s]+?\.)?(?:youtube\.com|youtu\.be|tiktok\.com|bilibili\.com|b23\.tv)[^\s]*?\+dwcc)', re.IGNORECASE)
    match = trigger_pattern.search(content)

    if match:
        full_url_with_tag = match.group(1)
        clean_url = full_url_with_tag.replace("+dwcc", "").strip()

        is_bili = "bilibili" in clean_url or "b23.tv" in clean_url
        is_yt = "youtube" in clean_url or "youtu.be" in clean_url
        is_tk = "tiktok" in clean_url

        if is_bili and not BOT_SETTINGS["allow_bilibili"]:
            return
        if is_yt and not BOT_SETTINGS["allow_youtube"]:
            return
        if is_tk and not BOT_SETTINGS["allow_tiktok"]:
            return

        try:
            menu_embed = discord.Embed(
                title="🔍 自动侦测云端下载服务",
                description="已成功自动侦测到网址！\n* 点击下方按钮将直接进行下载与云端托管。",
                color=discord.Color.blurple()
            )
            menu_embed.add_field(name="🔗 目标网址", value=clean_url, inline=False)
            
            view = DownloadView(url=clean_url)
            await message.author.send(embed=menu_embed, view=view)
            try:
                await message.delete()
            except:
                pass
        except Exception as e:
            print(f"发送私人 DM 失败（用户可能关闭私讯）: {e}")

    await bot.process_commands(message)

def upload_to_github_release(file_path: str) -> str:
    filename = os.path.basename(file_path)
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        TASK_STATUS["status"] = "uploading"
        TASK_STATUS["progress"] = 75
        TASK_STATUS["message"] = f"正在将档案上传至 GitHub 云端..."

        release_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/tags/{TAG_NAME}"
        resp = requests.get(release_url, headers=headers)
        
        if resp.status_code == 200:
            release_data = resp.json()
            upload_url_template = release_data["upload_url"]
        else:
            create_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases"
            payload = {
                "tag_name": TAG_NAME,
                "name": "Discord Bot Video Storage",
                "body": "Automated video storage for Discord media downloader bot."
            }
            create_resp = requests.post(create_url, headers=headers, json=payload)
            if create_resp.status_code != 201:
                print(f"建立 GitHub Release 失败: {create_resp.text}")
                return None
            release_data = create_resp.json()
            upload_url_template = release_data["upload_url"]

        base_upload_url = upload_url_template.split("{")[0]
        
        # 💡 核心修复：保持视频标题原名，并完美拼接毫秒级时间戳，彻底防止 GitHub 报 already_exists 错误
        safe_filename = filename.encode('utf-8', 'ignore').decode('utf-8')
        name_part, ext_part = os.path.splitext(safe_filename)
        timestamp = int(time.time() * 1000)
        safe_filename = f"{name_part}_{timestamp}{ext_part}"

        content_type = "audio/mpeg" if safe_filename.endswith(".mp3") else "video/mp4"
        with open(file_path, "rb") as f:
            file_data = f.read()

        upload_headers = headers.copy()
        upload_headers["Content-Type"] = content_type
        params = {"name": safe_filename}
        
        upload_resp = requests.post(base_upload_url, headers=upload_headers, params=params, data=file_data, timeout=300)
        if upload_resp.status_code == 201:
            asset_data = upload_resp.json()
            return asset_data.get("browser_download_url")
        else:
            print(f"上传档案至云端失败: {upload_resp.text}")
    except Exception as e:
        print(f"云端上传例外错误: {e}")
    return None

def shorten_url(long_url: str) -> str:
    try:
        api_url = f"https://is.gd/create.php?format=simple&url={urllib.parse.quote(long_url)}"
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            short_url = response.read().decode('utf-8').strip()
            if short_url.startswith("http"):
                return short_url
    except Exception as e:
        print(f"云端链接转换失败: {e}")
    return long_url

class DownloadResultView(discord.ui.View):
    def __init__(self, download_url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="📥 点击下载档案", style=discord.ButtonStyle.link, url=download_url))

class DownloadView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=120)
        self.url = url
        self.downloaded_file_path = None

    async def start_download(self, interaction: discord.Interaction, mode_text: str, is_mp3: bool):
        if interaction.guild and interaction.guild.id in DISABLED_GUILDS:
            await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: GUILD_DISABLED]", ephemeral=True)
            return

        is_bili = "bilibili.com" in self.url or "b23.tv" in self.url
        is_yt = "youtube.com" in self.url or "youtu.be" in self.url
        is_tk = "tiktok.com" in self.url

        if is_bili and not BOT_SETTINGS["allow_bilibili"]:
            await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: BILI_DISABLED]", ephemeral=True)
            return
        if is_yt and not BOT_SETTINGS["allow_youtube"]:
            await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: YT_DISABLED]", ephemeral=True)
            return
        if is_tk and not BOT_SETTINGS["allow_tiktok"]:
            await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: TK_DISABLED]", ephemeral=True)
            return

        if is_bili:
            self.url = self.url.split('?')[0]

        is_guild = interaction.guild is not None
        if is_guild:
            await interaction.response.defer(thinking=True, ephemeral=True)
        else:
            await interaction.response.defer(thinking=True)
        
        loading_embed = discord.Embed(
            title="⏳ 影音任务处理中...",
            description=f"进度：`正在下载 {mode_text}`\n请稍候...",
            color=discord.Color.gold()
        )
        loading_embed.add_field(name="⚙️ 处理模式", value=mode_text, inline=True)
        
        for child in self.children:
            child.disabled = True
        try:
            await interaction.edit_original_response(embed=loading_embed, view=self)
        except:
            pass

        TASK_STATUS["status"] = "downloading"
        TASK_STATUS["progress"] = 30
        TASK_STATUS["message"] = f"正在下载媒体 ({mode_text})..."

        yt_cookies_path = os.path.join(CURRENT_DIR, 'yt_cookies.txt')
        cookie_path = os.path.join(CURRENT_DIR, 'bili_cookies.txt')
        
        # 💡 使用标题作为档名模板（%(title)s），并强制转码为 iOS 相容的 H.264
        ydl_opts = {
            'ffmpeg_location': CURRENT_DIR,
            'socket_timeout': 30,
            'retries': 10,
            'format': 'bv*[height<=1080]+ba/b',
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(CURRENT_DIR, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': {
                'ffmpeg': ['-c:v', 'libx264', '-preset', 'fast', '-crf', '22', '-c:a', 'aac', '-b:a', '192k']
            }
        }

        if os.path.exists(yt_cookies_path):
            ydl_opts['cookiefile'] = yt_cookies_path

        if is_bili:
            if os.path.exists(cookie_path):
                ydl_opts['cookiefile'] = cookie_path
            ydl_opts.update({
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com',
                }
            })

        try:
            def run_ytdlp():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.url, download=True)
                    filename = ydl.prepare_filename(info)
                    base, _ = os.path.splitext(filename)
                    mp4_filename = base + ".mp4"

                    if is_mp3:
                        mp3_filename = base + ".mp3"
                        ffmpeg_cmd = [
                            os.path.join(CURRENT_DIR, 'ffmpeg.exe'),
                            '-y', '-i', mp4_filename,
                            '-vn', '-ab', '320k', '-ar', '44100', '-map', '0:a:0',
                            mp3_filename
                        ]
                        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                        
                        if os.path.exists(mp4_filename):
                            os.remove(mp4_filename)
                        return mp3_filename
                    else:
                        return mp4_filename

            loop = asyncio.get_running_loop()
            actual_filename = await loop.run_in_executor(None, run_ytdlp)

            if not actual_filename or not os.path.exists(actual_filename):
                raise FileNotFoundError("找不到下载完成的媒体档案。")

            self.downloaded_file_path = actual_filename
            file_size_mb = os.path.getsize(actual_filename) / (1024 * 1024)

            TASK_STATUS["total_downloaded_mb"] += file_size_mb
            TASK_STATUS["download_count"] += 1
            save_stats()

            github_url = None
            if BOT_SETTINGS["auto_upload"]:
                github_url = await loop.run_in_executor(None, upload_to_github_release, actual_filename)
            
            if github_url:
                short_link = shorten_url(github_url)
                await asyncio.sleep(1)

                TASK_STATUS["status"] = "success"
                TASK_STATUS["progress"] = 100
                TASK_STATUS["message"] = f"任务完成！档案大小: {file_size_mb:.2f} MB"
                
                success_embed = discord.Embed(
                    title="🎉 云端托管成功！",
                    description=f"已成功完成处理，并上传至云端。\n🔗 档案下载链接：{short_link}",
                    color=discord.Color.green()
                )
                success_embed.add_field(name="📄 处理模式", value=f"`{mode_text}`", inline=False)
                success_embed.add_field(name="📊 档案大小", value=f"{file_size_mb:.2f} MB", inline=True)
                
                result_view = DownloadResultView(short_link)
                if is_guild:
                    await interaction.followup.send(content=short_link, embed=success_embed, view=result_view, ephemeral=True)
                else:
                    await interaction.followup.send(content=short_link, embed=success_embed, view=result_view)
            else:
                raise Exception("云端托管上传失败或功能未开启。 [错误代码: UPLOAD_FAILED]")

        except Exception as e:
            TASK_STATUS["status"] = "error"
            TASK_STATUS["progress"] = 0
            
            err_str = str(e)
            short_err = err_str.split("\n")[0][:80] if err_str else "UNKNOWN_ERROR"
            TASK_STATUS["message"] = f"错误: {short_err}"

            err_embed = discord.Embed(
                title="❌ 处理失败", 
                description=f"请联系管理员回报问题\n* 错误摘要：`{short_err}`", 
                color=discord.Color.red()
            )
            try:
                if is_guild:
                    await interaction.followup.send(embed=err_embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=err_embed)
            except:
                pass
        finally:
            if self.downloaded_file_path and os.path.exists(self.downloaded_file_path):
                try:
                    os.remove(self.downloaded_file_path)
                except:
                    pass
            self.stop()

    @discord.ui.button(label="🎬 最高画质影片", style=discord.ButtonStyle.primary, row=0)
    async def best_video_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_download(interaction=interaction, mode_text="最高画质影片", is_mp3=False)

    @discord.ui.button(label="🎵 最高音质 MP3", style=discord.ButtonStyle.secondary, row=0)
    async def best_audio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_download(interaction=interaction, mode_text="最高音质 MP3", is_mp3=True)

@bot.tree.context_menu(name="机器人-下载档案")
async def download_message_context(interaction: discord.Interaction, message: discord.Message):
    if interaction.guild and interaction.guild.id in DISABLED_GUILDS:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: GUILD_DISABLED]", ephemeral=True)
        return

    match = URL_REGEX.search(message.content)
    if not match:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: URL_NOT_FOUND]", ephemeral=True)
        return
    url = match.group(0)

    is_bili = "bilibili.com" in url or "b23.tv" in url
    is_yt = "youtube.com" in url or "youtu.be" in url
    is_tk = "tiktok.com" in url

    if is_bili and not BOT_SETTINGS["allow_bilibili"]:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: BILI_DISABLED]", ephemeral=True)
        return
    if is_yt and not BOT_SETTINGS["allow_youtube"]:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: YT_DISABLED]", ephemeral=True)
        return
    if is_tk and not BOT_SETTINGS["allow_tiktok"]:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: TK_DISABLED]", ephemeral=True)
        return

    menu_embed = discord.Embed(title="🔍 云端下载服务已就绪", description="* 点击下方按钮将自动进行下载。", color=discord.Color.blurple())
    menu_embed.add_field(name="🔗 目标网址", value=url, inline=False)
    view = DownloadView(url=url)
    await interaction.response.send_message(embed=menu_embed, view=view, ephemeral=True)

@bot.tree.command(name="download", description="输入 YouTube / TikTok / B站 等影音网址，取得专属下载链接")
@app_commands.describe(url="请输入 YouTube / TikTok / B站 媒体网址")
async def download_slash(interaction: discord.Interaction, url: str):
    if interaction.guild and interaction.guild.id in DISABLED_GUILDS:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: GUILD_DISABLED]", ephemeral=True)
        return

    if not URL_REGEX.match(url):
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: INVALID_URL_FORMAT]", ephemeral=True)
        return

    is_bili = "bilibili.com" in url or "b23.tv" in url
    is_yt = "youtube.com" in url or "youtu.be" in url
    is_tk = "tiktok.com" in url

    if is_bili and not BOT_SETTINGS["allow_bilibili"]:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: BILI_DISABLED]", ephemeral=True)
        return
    if is_yt and not BOT_SETTINGS["allow_youtube"]:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: YT_DISABLED]", ephemeral=True)
        return
    if is_tk and not BOT_SETTINGS["allow_tiktok"]:
        await interaction.response.send_message("❌ 请联系管理员回报问题 [错误代码: TK_DISABLED]", ephemeral=True)
        return

    menu_embed = discord.Embed(title="🔍 云端下载服务已就绪", description="* 点击下方按钮将自动进行下载。", color=discord.Color.blurple())
    menu_embed.add_field(name="🔗 目标网址", value=url, inline=False)
    view = DownloadView(url=url)
    await interaction.response.send_message(embed=menu_embed, view=view, ephemeral=True)

def bridge_sync_loop():
    while True:
        try:
            if os.path.exists(COMMAND_FILE):
                with open(COMMAND_FILE, "r", encoding="utf-8") as f:
                    cmd = json.load(f)
                os.remove(COMMAND_FILE)
                
                action = cmd.get("action")
                if action == "toggle_guild":
                    g_id = int(cmd.get("guild_id"))
                    if cmd.get("enabled"):
                        if g_id in DISABLED_GUILDS: DISABLED_GUILDS.remove(g_id)
                        print(f"🟢 网页端已启用服务器 (ID: {g_id})")
                    else:
                        DISABLED_GUILDS.add(g_id)
                        print(f"🔴 网页端已关闭服务器 (ID: {g_id})")
                
                elif action == "leave_guild":
                    g_id = int(cmd.get("guild_id"))
                    guild = bot.get_guild(g_id)
                    if guild:
                        name = guild.name
                        asyncio.run_coroutine_threadsafe(guild.leave(), bot.loop)
                        if g_id in DISABLED_GUILDS: DISABLED_GUILDS.remove(g_id)
                        print(f"🚪 网页端已强制退出服务器: {name}")
                
                elif action == "update_settings":
                    new_settings = cmd.get("settings", {})
                    BOT_SETTINGS.update(new_settings)
                    print(f"⚙️ 网页端已更新功能设定: {BOT_SETTINGS}")
                
                elif action == "clear_logs":
                    LOG_BUFFER.clear()
                    print("🧹 网页端已清空系统日志")

            guilds_data = []
            if bot.is_ready():
                for g in bot.guilds:
                    guilds_data.append({
                        "id": str(g.id), 
                        "name": g.name, 
                        "count": g.member_count,
                        "disabled": g.id in DISABLED_GUILDS
                    })
            
            payload = {
                "timestamp": time.time(),
                "guilds": guilds_data,
                "settings": BOT_SETTINGS,
                "task": TASK_STATUS,
                "logs": list(LOG_BUFFER)
            }
            with open(BRIDGE_STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception as e:
            pass
        time.sleep(1)

if __name__ == "__main__":
    bridge_thread = threading.Thread(target=bridge_sync_loop, daemon=True)
    bridge_thread.start()
    print("🔄 机器人双向通桥接执行绪已启动...")

    bot.run(DISCORD_TOKEN)