import os
import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio
import json
from dotenv import load_dotenv
from discord.errors import Forbidden

# .env 파일에서 환경변수를 로드합니다.
load_dotenv()
# TOKEN은 .env 파일에서 가져옵니다.
TOKEN = os.getenv("TOKEN")

# config.json 파일을 읽어 봇 설정을 불러옵니다.
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# 봇에서 필요한 Intents 설정 (메시지 내용 및 멤버 이벤트 접근 허용)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 명령어 접두사는 '/'로 설정합니다.
bot = commands.Bot(command_prefix='/', intents=intents)

# -----------------------------------------------------------------
# TicketView 클래스
# - 티켓 채널 내에서 사용되는 뷰로 "닫기" 버튼과 "지급" 버튼이 포함되어 있습니다.
# - "닫기" 버튼: 5초 카운트다운 후 채널을 삭제합니다.
# - "지급" 버튼: 관리자가 클릭 시 티켓 생성자에게 지정된 역할을 부여합니다.
# -----------------------------------------------------------------
class TicketView(View):
    def __init__(self, author_id: int):
        # 타임아웃 없이 버튼이 계속 작동하도록 설정합니다.
        super().__init__(timeout=None)
        # 티켓을 생성한 플레이어의 ID를 저장합니다.
        self.author_id = author_id

    @discord.ui.button(label="닫기", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 버튼 클릭 시, 먼저 interaction을 지연(Defer) 처리하여 이후 수정 작업이 가능하도록 합니다.
        await interaction.response.defer()
        # 5초간 카운트다운을 진행하며 embed를 업데이트합니다.
        for remaining in range(5, 0, -1):
            # 남은 시간을 표시하는 embed 생성
            embed = discord.Embed(title="티켓 종료", description=f"{remaining}초 후 티켓이 종료됩니다.")
            # 버튼이 포함된 원본 메시지를 수정하여 카운트다운 업데이트
            await interaction.message.edit(embed=embed)
            await asyncio.sleep(1)
        # 카운트다운이 완료되면 티켓 채널을 삭제합니다.
        await interaction.channel.delete()

    @discord.ui.button(label="지급", style=discord.ButtonStyle.success, custom_id="award_role")
    async def award_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 지급 버튼 클릭 시, 관리자인지 확인하기 위해 사용자의 역할 ID 목록을 확인합니다.
        admin_role_ids = config.get("admin_role_ids", [])
        user_role_ids = [role.id for role in interaction.user.roles]
        if not any(admin_id in user_role_ids for admin_id in admin_role_ids):
            # 관리자가 아니라면 에페머럴(비공개) 메시지로 권한 없음 안내
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        
        guild = interaction.guild
        # 티켓을 생성한 플레이어(member)를 guild에서 찾습니다.
        member = guild.get_member(self.author_id)
        # 지급할 역할(role)을 config의 award_role_id로부터 가져옵니다.
        role = guild.get_role(config["award_role_id"])
        if member and role:
            try:
                # 티켓 생성자에게 역할 부여 시도 (봇 권한 및 역할 순서를 확인하세요)
                await member.add_roles(role)
                await interaction.response.send_message(f"{member.mention}님에게 역할이 지급되었습니다.", ephemeral=True)
            except Forbidden:
                # 봇의 권한 부족 등으로 역할 지급에 실패한 경우
                await interaction.response.send_message("역할 지급에 실패하였습니다. 봇의 권한을 확인하세요.", ephemeral=True)
        else:
            await interaction.response.send_message("역할 지급에 실패하였습니다.", ephemeral=True)

# -----------------------------------------------------------------
# AnnouncementView 클래스
# - 공지 채널에 안내 임베드와 "홍보이벤트참여" 버튼을 표시합니다.
# - 플레이어가 "홍보이벤트참여" 버튼을 누르면 티켓 채널이 생성됩니다.
# - 티켓 채널은 config에 지정된 카테고리 하위에 생성되며,
#   생성 후 티켓 채널 태그만 에페머럴 메시지로 사용자에게 전달됩니다.
# -----------------------------------------------------------------
class AnnouncementView(View):
    def __init__(self):
        # 타임아웃 없이 버튼이 계속 작동하도록 설정합니다.
        super().__init__(timeout=None)
    
    @discord.ui.button(label="홍보이벤트참여", style=discord.ButtonStyle.primary, custom_id="join_event")
    async def join_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        # interaction 객체를 통해 상호작용이 발생한 서버(guild)에 접근합니다.
        guild = interaction.guild
        
        # config에 지정된 티켓 카테고리의 채널 객체를 가져옵니다.
        category = guild.get_channel(config["ticket_category_id"])
        
        # 새 티켓 채널을 생성합니다.
        # 채널 이름은 "ticket-사용자이름" 형식으로 생성되며, 지정된 카테고리 하위에 생성됩니다.
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category
        )
        
        # 티켓 채널 내부에 표시될 안내 임베드를 생성합니다.
        embed_ticket = discord.Embed(title="홍보이벤트 티켓", description="홍보 자료를 업로드 해주세요.")
        
        # 티켓 채널 내에서 사용할 TicketView(닫기, 지급 버튼 포함) 객체를 생성합니다.
        ticket_view = TicketView(author_id=interaction.user.id)
        
        # 생성된 티켓 채널에 안내 임베드와 TicketView를 전송합니다.
        await ticket_channel.send(embed=embed_ticket, view=ticket_view)
        
        # 에페머럴 메시지로 티켓 채널 태그와 함께 안내 메시지를 사용자에게 전달합니다.
        # 안내 메시지에는 티켓이 생성되었음을 알리고, 홍보 자료 업로드를 위해 티켓 채널을 확인하라는 내용이 포함됩니다.
        await interaction.response.send_message(
            f"티켓 채널이 생성되었습니다. 아래 채널에서 홍보 자료를 업로드 해주세요:\n{ticket_channel.mention}",ephemeral=True)

        

# -----------------------------------------------------------------
# 봇 준비 이벤트
# - 봇이 준비되면 config에 지정된 공지 채널에 안내 메시지와 AnnouncementView를 전송합니다.
# -----------------------------------------------------------------
@bot.event
async def on_ready():
    print("봇이 준비되었습니다.")
    # config에 지정된 공지 채널 객체를 가져옵니다.
    channel = bot.get_channel(config["announcement_channel_id"])
    # 안내 임베드를 생성합니다.
    embed = discord.Embed(title="홍보 이벤트 안내", description="참여를 원하시면 '홍보이벤트참여' 버튼을 눌러주세요.")
    # 공지 채널에 안내 임베드와 AnnouncementView를 전송합니다.
    await channel.send(embed=embed, view=AnnouncementView())

# 봇 실행 (.env 파일에서 불러온 토큰 사용)
bot.run(TOKEN)
