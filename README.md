# ombor_service_bot

Ombor xizmati Telegram boti — mijoz va xodimlar uchun tez ariza, guruhda qabul qilish, hisobotlar.

## Imkoniyatlar

**Mijoz (shaxsiy chat):**
- 🙋 Iltimos, xizmat ko'rsating (tez chaqiruv)
- 👀 Ombordagi mijozga qarang (tez chaqiruv)
- 📦 Tovar buyurtma
- 📋 Mahsulot olib keling
- ⭐ VIP / Shoshilinch
- ⚠️ Muammo / shikoyat
- ℹ️ Savol
- 📋 Mening arizalarim

**Guruh (ombor jamoasi):**
- Har bir ariza uchun tugmalar: **Qabul qilish**, **Jarayonda**, **Bajarildi**, **Rad etish**
- Holat o'zgarganda mijozga avtomatik xabar
- `/stat`, `/hisobot`, `/report` — kunlik va umumiy hisobot

## Railway variables

```
BOT_TOKEN=...
GROUP_ID=-1003934348711
ADMIN_IDS=123456789,987654321
```

- `GROUP_ID` — ombor ishchi guruhi (majburiy)
- `ADMIN_IDS` — ixtiyoriy; `/orders` va shaxsiy hisobot uchun

Botni guruhga qo'shing va **admin** qiling. Guruh ID: guruhda `/id`.

## Ishga tushirish

```bash
pip install -r requirements.txt
cp env.example .env
python main.py
```

## Buyruqlar

| Buyruq | Kim | Vazifa |
|--------|-----|--------|
| `/start` | Hamma | Asosiy menyu |
| `/menu` | Hamma | Menyuga qaytish |
| `/cancel` | Hamma | Bekor qilish |
| `/id` | Hamma | Chat ID |
| `/stat` | Guruh | Bugungi hisobot |
| `/orders` | Admin | Oxirgi arizalar |
