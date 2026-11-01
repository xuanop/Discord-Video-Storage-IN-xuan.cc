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
from collections import deque
import discord
from discord import app_commands
from discord.ext import commands

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
STATS_FILE = os.path.join(CURRENT_DIR, 'download_stats.txt')

BOT_SETTINGS = {
    "allow_bilibili": True,
    "allow_youtube": True,
    "allow_tiktok": True,
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
    print(f"✨ 影音下载机器人（Discord 直链版）已上线：{bot.user}")

def trigger_github_action(video_url: str, file_name: str) -> bool:
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/actions/workflows/download.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    payload = {
        "ref": "main",
        "inputs": {
            "video_url": video_url,
            "file_name": file_name
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        return response.status_code == 204
    except Exception as e:
        print(f"触发 GitHub Actions 异常: {e}")
        return False

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
        self.add_item(discord.ui.Button(label="📥 点击直接下载文件", style=discord.ButtonStyle.link, url=download_url))

class DownloadView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=120)
        self.url = url

    async def start_download(self, interaction: discord.Interaction, mode_text: str, is_mp3: bool):
        # 1. 立即 Defer 彻底防止 10062 错误
        is_guild = interaction.guild is not None
        if is_guild:
            await interaction.response.defer(thinking=True, ephemeral=True)
        else:
            await interaction.response.defer(thinking=True)

        # 2. 本地智能展开 B站短链接
        if "bilibili.com" in self.url or "b23.tv" in self.url:
            if "b23.tv" in self.url:
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    resp = requests.get(self.url, allow_redirects=True, timeout=10, headers=headers)
                    self.url = resp.url.split('?')[0]
                    print(f"成功将 B站短链接展开为长链接: {self.url}")
                except Exception as e:
                    print(f"展开 B站短链接异常: {e}")
            else:
                self.url = self.url.split('?')[0]

        loading_embed = discord.Embed(
            title="⏳ 正在派发云端直链任务...",
            description=f"处理模式：`{mode_text}`\n正在向云端后台发送请求，请稍候...",
            color=discord.Color.gold()
        )
        
        for child in self.children:
            child.disabled = True
        try:
            await interaction.edit_original_response(embed=loading_embed, view=self)
        except:
            pass

        try:
            ext = "mp3" if is_mp3 else "mp4"
            file_name = f"media_{int(time.time())}.{ext}"
            raw_direct_url = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/download/{TAG_NAME}/{file_name}"

            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, trigger_github_action, self.url, file_name)

            if not success:
                raise Exception("无法成功触发 GitHub Actions 云端任务 [错误代码: TRIGGER_FAILED]")

            TASK_STATUS["download_count"] += 1
            save_stats()

            short_link = shorten_url(raw_direct_url)
            await asyncio.sleep(1)

            success_embed = discord.Embed(
                title="🚀 文件直链已生成！",
                description=f"后台正在为您高速下载与合流中。\n* 请等待 **30 秒 - 1 分钟** 后，点击下方按钮**直接下载文件**：",
                color=discord.Color.green()
            )
            success_embed.add_field(name="🔗 直链地址", value=short_link, inline=False)
            success_embed.add_field(name="📄 模式", value=f"`{mode_text}`", inline=False)
            
            result_view = DownloadResultView(short_link)
            if is_guild:
                await interaction.followup.send(content=short_link, embed=success_embed, view=result_view, ephemeral=True)
            else:
                await interaction.followup.send(content=short_link, embed=success_embed, view=result_view)

        except Exception as e:
            err_str = str(e)
            short_err = err_str.split("\n")[0][:80] if err_str else "UNKNOWN_ERROR"
            err_embed = discord.Embed(title="❌ 任务派发失败", description=f"错误摘要：`{short_err}`", color=discord.Color.red())
            if is_guild:
                await interaction.followup.send(embed=err_embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=err_embed)
        finally:
            self.stop()

    @discord.ui.button(label="🎬 最高画质影片 (MP4)", style=discord.ButtonStyle.primary, row=0)
    async def best_video_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_download(interaction=interaction, mode_text="最高画质影片 (MP4)", is_mp3=False)

    @discord.ui.button(label="🎵 最高音质 (MP3)", style=discord.ButtonStyle.secondary, row=0)
    async def best_audio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_download(interaction=interaction, mode_text="最高音质 (MP3)", is_mp3=True)

@bot.tree.command(name="download", description="输入影音网址，选择下载 MP4 或 MP3 直链")
@app_commands.describe(url="请输入 YouTube / TikTok / B站 媒体网址")
async def download_slash(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    if not URL_REGEX.match(url):
        await interaction.followup.send("❌ 网址格式不正确", ephemeral=True)
        return

    menu_embed = discord.Embed(title="🔍 请选择您要生成的档案类型", description="* 点击下方按钮立刻派发云端直链任务。", color=discord.Color.blurple())
    menu_embed.add_field(name="🔗 目标网址", value=url, inline=False)
    view = DownloadView(url=url)
    await interaction.followup.send(embed=menu_embed, view=view, ephemeral=True)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
