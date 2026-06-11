# IT Market Bot - BotHost Deployment Guide

## 🚀 Quick Start on BotHost

### Prerequisites
- BotHost account
- Telegram Bot Token (from @BotFather)
- PostgreSQL database
- Admin Telegram IDs

### Deployment Steps

1. **Create new application on BotHost**
   - Name: `IT-Market-Bot`
   - Runtime: Python 3.10

2. **Set Environment Variables**
   ```
   BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   ADMIN_IDS=123456789,987654321
   DATABASE_URL=postgresql+psycopg2://user:password@host:5432/it_market_bot
   USE_WEBHOOK=false
   WEBHOOK_URL=https://your-domain.com/webhook (if using webhook)
   ```

3. **Configure GitHub Integration**
   - Connect repository: `d3023232-cloud/itbot`
   - Branch: `main`
   - Auto-deploy: enabled

4. **Set Entry Point**
   - Entry Point: `app.py`
   - Or use: `python3 start.py`

5. **Deploy**
   - Click "Deploy"
   - Wait for build and start

### Logs
- Check BotHost dashboard for real-time logs
- Entry point script will automatically install dependencies

---

## 📁 File Structure

```
IT-Market-Bot/
├── app.py                 # Main bot entry point ✅
├── start.py               # BotHost startup script ✅
├── setup.py               # Setup script for dependencies ✅
├── entrypoint.sh          # Bash entry point
├── requirements.txt       # Python dependencies ✅
├── Procfile               # Process file ✅
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker compose
├── bothost-deploy.yml     # BotHost config ✅
├── bothost.yml            # BotHost manifest
├── app.yaml               # Google App Engine config
├── .env.example           # Environment template ✅
├── config.py              # Configuration
├── database.py            # Database
├── models.py              # SQLAlchemy models
├── handlers/              # All handlers
│   ├── admin_panel.py     # Admin panel ✅
│   ├── user.py
│   ├── admin.py
│   ├── developer.py
│   ├── messages.py
│   └── completion.py
├── keyboards/             # Keyboard layouts
├── utils/                 # Utilities
└── README.md
```

---

## ⚙️ Troubleshooting

### "ModuleNotFoundError: No module named 'aiogram'"
- **Solution:** Use `python3 start.py` as entry point, or check `requirements.txt` is deployed

### "DATABASE_URL not set"
- **Solution:** Add `DATABASE_URL` to BotHost environment variables

### "No module named 'config'"
- **Solution:** Make sure all Python files are uploaded, run `python3 setup.py`

### Bot doesn't respond
- **Solution:** Check `/admin` command, verify `ADMIN_IDS` is set correctly

---

## 🔐 Admin Panel

Access with: `/admin`

**Features:**
- 🔍 Find orders by ID or number
- 👤 Find users by ID or username
- 🚫 Ban/unban users
- 👥 Assign roles
- 📢 Broadcast messages
- 📊 View statistics
- 💰 Financial reports

---

## 🛠️ Alternative Deployment Methods

### Using Docker
```bash
docker-compose up -d
```

### Using Heroku
1. Push to Heroku
2. Set environment variables
3. Scale worker: `heroku ps:scale worker=1`

### Local Development
```bash
pip install -r requirements.txt
python3 app.py
```

---

## 📞 Support

For issues, check:
1. BotHost logs
2. Environment variables
3. PostgreSQL connection
4. Bot token validity

---

**Version:** 1.0.0  
**Last Updated:** June 2026
