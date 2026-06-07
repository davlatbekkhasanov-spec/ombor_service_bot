# ombor_service_bot

Ombor xizmati Telegram boti — mijoz va xodimlar uchun tez ariza, guruhda qabul qilish, hisobotlar.

## Imkoniyatlar

**Mijoz (shaxsiy chat):**
- 🙋 Iltimos, xizmat ko'rsating (tez chaqiruv)
- 👀 Ombordagi mijozga qarang (tez chaqiruv)
- 📦 Tovar buyurtma
- ℹ️ Savol

**Guruh (ombor jamoasi):**
- **👷 Men xizmat ko'rsataman** — xodim arizani band qiladi (boshqasi ololmaydi)
- **✔️ Xizmat tugadi** — faqat band qilgan xodim tugatadi
- Avtomatik: **kim xizmat ko'rsatdi** + **necha daqiqa** hisoblanadi
- `/stat`, `/hisobot` — xodimlar bo'yicha hisobot ham bor

## Railway variables

```
BOT_TOKEN=...
GROUP_ID=-1003934348711
ADMIN_IDS=123456789,987654321
```

- `GROUP_ID` — ombor ishchi guruhi (majburiy)
- `ADMIN_IDS` — ixtiyoriy; `/orders` va shaxsiy hisobot uchun
- `TICK_SEC=15` — LIVE tekshiruv intervali (kamida 10)
- `LIVE_EDIT_SEC=20` — bir ariza xabarini qayta edit qilish intervali (flood oldini oladi)

**Muhim:** ombor va kanstik tekshiruv botlarini **alohida guruhlarga** qo'ying — bir guruhda ikkala bot flood limitiga tez uriladi.

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
| `/seedstatus` | Admin | Seed va DB holati |
