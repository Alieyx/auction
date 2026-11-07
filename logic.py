import discord
from discord.ext import commands, tasks
from logic import DatabaseManager, hide_img
from config import TOKEN, DATABASE
import os

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

manager = DatabaseManager(DATABASE)
manager.create_tables()

# Bot ayarları (Yönetici komutlarıyla değiştirilebilir)
BONUS_REWARD = 10
MARKET_COST = 30

@bot.command()
async def start(ctx):
    user_id = ctx.author.id
    if user_id in manager.get_users():
        await ctx.send("Zaten kayıtlısınız!")
    else:
        manager.add_user(user_id, ctx.author.name)
        await ctx.send("""Merhaba! Hoş geldiniz! Başarılı bir şekilde kaydoldunuz! Her dakika yeni resimler alacaksınız ve bunları elde etme şansınız olacak! Bunu yapmak için “Al!” butonuna tıklamanız gerekiyor! Sadece “Al!” butonuna tıklayan ilk üç kullanıcı resmi alacaktır! =)""")

@tasks.loop(minutes=1)
async def send_message():
    prize = manager.get_random_prize()
    if not prize:
        return
    prize_id, img = prize[:2]
    hide_img(img)
    for user_id in manager.get_users():
        user = await bot.fetch_user(user_id) 
        if user:
            await send_image(user, f'hidden_img/{img}', prize_id)
    manager.mark_prize_used(prize_id)

async def send_image(user, image_path, prize_id):
    with open(image_path, 'rb') as img:
        file = discord.File(img)
        button = discord.ui.Button(label="Al!", custom_id=str(prize_id))
        view = discord.ui.View()
        view.add_item(button)
        await user.send(file=file, view=view)

@bot.command()
async def rating(ctx):
    res = manager.get_rating()
    res = [f'| @{x[0]:<11} | {x[1]:<11}|\n{"_"*26}' for x in res]
    res = '\n'.join(res)
    res = f'|USER_NAME    |COUNT_PRIZE|\n{"_"*26}\n' + res
    await ctx.send(f"```\n{res}\n```")

# --- BONUS PUAN VE MARKET KOMUTLARI ---

@bot.command()
async def puan(ctx):
    pts = manager.get_user_points(ctx.author.id)
    await ctx.send(f"Mevcut bonus puanınız: **{pts}**  (Marketten özel resim almak için `{MARKET_COST}` puan gerekir: `!market`)")

@bot.command()
async def market(ctx):
    user_id = ctx.author.id
    missed = manager.get_missed_prize(user_id)
    if not missed:
        await ctx.send("Tebrikler, şu ana kadarki tüm resimleri zaten toplamışsınız!")
        return

    if manager.spend_points(user_id, MARKET_COST):
        prize_id, img = missed
        manager.add_winner(user_id, prize_id, bonus_points=0)
        with open(f'img/{img}', 'rb') as photo:
            file = discord.File(photo)
            await ctx.send(file=file, content=f" **{MARKET_COST} bonus puan** harcayarak kaçırdığınız özel bir resmi aldınız!")
    else:
        pts = manager.get_user_points(user_id)
        await ctx.send(f"Yetersiz bonus puan! Mevcut puanınız: **{pts}**, gereken: **{MARKET_COST}**.")

# --- YÖNETİCİ KOMUTLARI ---

@bot.command()
@commands.has_permissions(administrator=True)
async def sure_ayarla(ctx, dakika: int):
    if dakika < 1:
        await ctx.send("Süre en az 1 dakika olmalıdır!")
        return
    send_message.change_interval(minutes=dakika)
    await ctx.send(f"✅ Resim gönderme sıklığı **{dakika} dakika** olarak güncellendi!")

@bot.command()
@commands.has_permissions(administrator=True)
async def bonus_ayarla(ctx, miktar: int):
    global BONUS_REWARD
    BONUS_REWARD = miktar
    await ctx.send(f"✅ Kazanılan açık artırma başına verilen bonus ödülü **{BONUS_REWARD} puan** olarak ayarlandı!")

@bot.command()
@commands.has_permissions(administrator=True)
async def resim_ekle(ctx):
    if not ctx.message.attachments:
        await ctx.send("Lütfen komutu kullanırken mesajınıza en az bir resim ekleyin!")
        return
    
    os.makedirs('img', exist_ok=True)
    eklenenler = []
    for attachment in ctx.message.attachments:
        if attachment.filename.endswith(('.png', '.jpg', '.jpeg')):
            file_path = os.path.join('img', attachment.filename)
            await attachment.save(file_path)
            eklenenler.append((attachment.filename,))
    
    if eklenenler:
        manager.add_prize(eklenenler)
        await ctx.send(f"✅ **{len(eklenenler)}** yeni resim başarıyla veri tabanına ve açık artırma havuzuna eklendi!")
    else:
        await ctx.send("Geçerli bir resim dosyası (.png, .jpg, .jpeg) bulunamadı.")

@bot.event
async def on_interaction(interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data['custom_id']
        user_id = interaction.user.id

        if manager.get_winners_count(custom_id) < 3:
            res = manager.add_winner(user_id, custom_id, bonus_points=BONUS_REWARD)
            if res:
                img = manager.get_prize_img(custom_id)
                with open(f'img/{img}', 'rb') as photo:
                    file = discord.File(photo)
                    await interaction.response.send_message(
                        file=file, 
                        content=f"Tebrikler, resmi aldınız ve **+{BONUS_REWARD} bonus puan** kazandınız! "
                    )
            else:
                await interaction.response.send_message(content="Bu resme zaten sahipsiniz!", ephemeral=True)
        else:
            await interaction.response.send_message(content="Maalesef, birisi bu resmi çoktan aldı...", ephemeral=True)

@bot.event
async def on_ready():
    print(f'{bot.user} olarak giriş yapıldı!')
    if not send_message.is_running():
        send_message.start()

bot.run(TOKEN)