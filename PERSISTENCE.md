# Deploydan keyin ma'lumot yo'qolmasin

## Railway Volume (MAJBURIY — bir marta)

1. Railway → `ombor_service_bot` servisi
2. **Volumes** → **Add Volume** → Mount path: **`/data`**
3. Variables:
   ```
   DB_PATH=/data/orders.db
   TZ=Asia/Tashkent
   YORDAMCHI_HUB_URL=...
   YORDAMCHI_HUB_SECRET=...
   ```

## Avtomatik (kod)

- Eski `orders.db` → `/data/orders.db` migratsiya
- Har start: `/data/backups/startup_*.db`
- Hub ga kunlik jami vaqt (0 ga tushmaydi)
