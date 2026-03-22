# Telegram Alerts Setup & Troubleshooting

## ✅ NOW WORKS FOR BOTH PAPER AND REAL TRADING

Telegram alerts now send for ALL trades in both paper and real mode!

## What You'll Receive

### Paper Trading Mode
```
🟢 [PAPER] BUY BONK
Size: 0.22 SOL
Entry: $0.00001234
Target: 10x
Mode: Paper Trading

🚀 [PAPER] SELL BONK
Reason: trailing_stop_p2
P&L: +150.5%
Realized: +0.33 SOL
Mode: Paper Trading
```

### Real Trading Mode
```
🟢 BUY BONK
Size: 0.22 SOL
Entry: $0.00001234
Target: 10x
tx: 5xKXtg2CWz...

🚀 SELL BONK (trailing_stop_p2)
P&L: +150.5%
Received: 0.55 SOL
tx: 7xMNop3DYz...
```

### Daily Summaries
```
📊 Daily Summary
Trades: 5 (3 wins, 2 losses)
P&L: +1.25 SOL (+125%)
Balance: 2.25 SOL
```

### Warnings
```
⚠️ WARNING: Daily loss at -22.5% — approaching limit!

🚀 BIG WIN: Daily P&L at +65.3% (+0.85 SOL)!
```

### Bot Status
```
🚀 Solana Sniper Bot started!

🛑 Solana Sniper Bot stopped.
```

## Setup Instructions

### Step 1: Create Telegram Bot

1. **Open Telegram** and search for `@BotFather`

2. **Send command**: `/newbot`

3. **Follow prompts**:
   ```
   BotFather: Alright, a new bot. How are we going to call it?
   You: My Sniper Bot
   
   BotFather: Good. Now let's choose a username for your bot.
   You: my_sniper_bot_123
   
   BotFather: Done! Your token is: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

4. **Copy the token** (the long string after "Your token is:")

### Step 2: Get Your Chat ID

1. **Message your bot** (search for your bot's username in Telegram)

2. **Send any message** (e.g., "Hello")

3. **Visit this URL** in your browser (replace TOKEN with your bot token):
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```
   
   Example:
   ```
   https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/getUpdates
   ```

4. **Find your chat_id** in the response:
   ```json
   {
     "ok": true,
     "result": [{
       "message": {
         "chat": {
           "id": 987654321,  ← This is your chat_id
           "first_name": "Your Name"
         }
       }
     }]
   }
   ```

5. **Copy the chat_id** (the number, e.g., 987654321)

### Step 3: Add to .env

Open your `.env` file and add:

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321
```

**Important:** 
- No quotes around the values
- No spaces
- Chat ID is just the number (no quotes)

### Step 4: Test

```bash
python main.py
```

You should immediately receive:
```
🚀 Solana Sniper Bot started!
```

## Troubleshooting

### Not Receiving Any Messages

#### Check 1: Verify .env Configuration
```bash
# Open .env and verify:
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz  ✅
TELEGRAM_CHAT_ID=987654321  ✅

# Common mistakes:
TELEGRAM_BOT_TOKEN=""  ❌ (empty)
TELEGRAM_CHAT_ID="987654321"  ❌ (has quotes)
TELEGRAM_BOT_TOKEN=123456789  ❌ (missing full token)
```

#### Check 2: Test Telegram Connection
```bash
# Run this in Python to test:
python3 -c "
import requests
TOKEN = 'YOUR_BOT_TOKEN'
CHAT_ID = 'YOUR_CHAT_ID'
url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
response = requests.post(url, json={'chat_id': CHAT_ID, 'text': 'Test'})
print(response.json())
"
```

**Expected output:**
```json
{"ok": true, "result": {...}}
```

**If you get an error:**
- `"error_code": 401` → Wrong bot token
- `"error_code": 400` → Wrong chat ID
- `"error_code": 403` → You haven't messaged the bot yet

#### Check 3: Message the Bot First
You MUST send at least one message to your bot before it can message you.

1. Search for your bot in Telegram
2. Click "Start" or send any message
3. Restart the sniper bot

#### Check 4: Check Logs
```bash
tail -f data/logs/bot.log
```

Look for:
```
[ERROR] Failed to send Telegram message: ...
```

### Receiving Startup Message But No Trade Alerts

#### Possible Causes:

1. **No Trades Happening**
   - Bot is running but no coins passing filters
   - Check logs for `[ANALYSIS] ✅ PASS` messages
   - If no passes, filters might be too strict

2. **Paper Mode with No Activity**
   - Paper mode needs real market activity to trigger
   - Wait for coins to be detected and analyzed

3. **Telegram Function Not Wired**
   - Should be automatic, but verify in logs
   - Look for `[EXECUTOR] ✅ BUY` messages

### Messages Delayed

#### Cause: Telegram Rate Limits
- Telegram limits: 30 messages per second
- Bot sends async (shouldn't be an issue)

#### Solution:
- Normal behavior if many trades happening
- Messages will arrive, just slightly delayed

### Wrong Chat Receiving Messages

#### Cause: Wrong Chat ID
- You copied someone else's chat ID
- You're in a group chat

#### Solution:
1. Make sure you messaged YOUR bot
2. Get YOUR chat ID from `/getUpdates`
3. Use YOUR personal chat ID (not a group)

## Testing Checklist

- [ ] Created bot with @BotFather
- [ ] Got bot token
- [ ] Messaged the bot (sent "Hello")
- [ ] Got chat ID from `/getUpdates`
- [ ] Added both to `.env` (no quotes on chat ID)
- [ ] Restarted bot
- [ ] Received "Bot started!" message
- [ ] Waiting for trade alerts

## Alert Frequency

### Paper Mode:
- ✅ Every buy (when position opens)
- ✅ Every sell (when position closes)
- ✅ Daily summary (once per day)
- ✅ Big wins/losses (>50% or <-20%)
- ✅ Bot start/stop

### Real Mode:
- ✅ Every buy (with transaction hash)
- ✅ Every sell (with transaction hash)
- ✅ Daily summary (once per day)
- ✅ Big wins/losses (>50% or <-20%)
- ✅ Bot start/stop

## Privacy & Security

### Bot Token Security:
- ⚠️ Never share your bot token
- ⚠️ Never commit `.env` to git
- ⚠️ Token gives full control of your bot

### Chat ID Security:
- ✅ Chat ID is less sensitive
- ✅ But still keep it private
- ✅ Someone with your chat ID can't control your bot

### Revoking Access:
If your token is compromised:
1. Message @BotFather
2. Send `/mybots`
3. Select your bot
4. Click "API Token"
5. Click "Revoke current token"
6. Get new token and update `.env`

## Advanced: Group Alerts

### Send to Telegram Group:

1. **Create a group** in Telegram

2. **Add your bot** to the group

3. **Make bot admin** (optional, for posting)

4. **Get group chat ID**:
   - Send a message in the group
   - Visit: `https://api.telegram.org/botTOKEN/getUpdates`
   - Look for `"chat":{"id":-123456789` (negative number)
   - Use the negative number as CHAT_ID

5. **Update .env**:
   ```bash
   TELEGRAM_CHAT_ID=-123456789
   ```

Now all alerts go to the group!

## Example .env Configuration

```bash
# Telegram Alerts (Optional but Recommended)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# Or for group:
# TELEGRAM_CHAT_ID=-987654321
```

## Summary

✅ **Telegram alerts now work for BOTH paper and real trading**  
✅ **All trades send alerts (not just >50% P&L)**  
✅ **Daily summaries included**  
✅ **Bot status notifications**  
✅ **Easy setup with @BotFather**  

**If you're not receiving messages:**
1. Check `.env` has both TOKEN and CHAT_ID
2. Make sure you messaged the bot first
3. Verify with test script above
4. Check logs for errors

---

**Status**: ✅ Fully Working  
**Modes**: Paper & Real  
**Setup Time**: 5 minutes
