#!/usr/bin/env python3
"""
Telegram Auto-Add Server - Multi-Server Ranking System
5 Servers with REAL Verified Statistics via Admin Account Detection
Each server has its own admin account that verifies worker adds
Automatic dead account removal + Fixed chat loading
"""

from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest, GetParticipantsRequest
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.functions.messages import GetDialogsRequest, GetHistoryRequest
from telethon.tl.types import (
    InputPeerEmpty, ChannelParticipantsSearch, 
    PeerChannel, PeerUser, PeerChat,
    MessageMediaPhoto, MessageMediaDocument,
    MessageMediaWebPage, DocumentAttributeFilename,
    User, InputPeerUser, InputPeerChat, InputPeerChannel,
    DialogFilter, InputDialogPeer
)
from telethon.sessions import StringSession
from telethon.tl.types.channel_participants import ChannelParticipantsRecent
import json
import os
import asyncio
import logging
import time
import random
import threading
import requests
from datetime import datetime, timedelta
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ============================================
# CHANGE ONLY THIS NUMBER PER SERVER
# ============================================
SERVER_NUMBER = 5  # 1=Dil, 2=sofu, 3=bebby, 4=kaleb, 5=fitsum

# ============================================
# ALL CREDENTIALS HARDCODED - 5 SERVERS
# ============================================
SERVERS = {
    1: {
        'name': 'Dil',
        'api_id': 35790598,
        'api_hash': 'fa9f62d821f04b03d76d53175e367736',
        'url': 'https://dilbedil.onrender.com'
    },
    2: {
        'name': 'sofu',
        'api_id': 36274756,
        'api_hash': 'b70311a2b3547e1ce40e72081dc726dc',
        'url': 'https://sofuu.onrender.com'
    },
    3: {
        'name': 'bebby',
        'api_id': 31590358,
        'api_hash': '072edc73e0f4003ddcba1c41d24adb02',
        'url': 'https://bebby.onrender.com'
    },
    4: {
        'name': 'kaleb',
        'api_id': 37539842,
        'api_hash': 'a9927e01c5023bf828fe753895d5731b',
        'url': 'https://kaleb.onrender.com'
    },
    5: {
        'name': 'fitsum',
        'api_id': 33441396,
        'api_hash': 'e6b64536883a7cd95aeb06c73faa1c95',
        'url': 'https://fitsum.onrender.com'
    }
}

# Bot for reports
BOT_TOKEN = '7930542124:AAFg5O4KUu7QFORVkxzowtG0nHAiX0yXXBY'
REPORT_CHAT_ID = '-1002452548749'
TARGET_GROUP = 'Abe_armygroup'

# Pick current server
CFG = SERVERS.get(SERVER_NUMBER, SERVERS[1])
SERVER_NAME = CFG['name']
API_ID = CFG['api_id']
API_HASH = CFG['api_hash']
SERVER_URL = CFG['url']

OTHER_SERVERS = [{'name': SERVERS[i]['name'], 'url': SERVERS[i]['url'], 'num': i} for i in SERVERS if i != SERVER_NUMBER]

PORT = int(os.environ.get('PORT', 10000))

# ============================================
# STORAGE
# ============================================
accounts = []
temp_sessions = {}
auto_add_settings = {}
active_clients = {}
running_tasks = {}

# Worker add tracking
worker_adds = defaultdict(list)

# Admin linked account per server
server_admin = {}

stats = {
    'total_added': 0,
    'today_added': 0,
    'verified_total': 0,
    'verified_today': 0,
    'last_reset': datetime.now().strftime('%Y-%m-%d'),
    'last_verification': None,
    'daily_history': {},
    'worker_stats': {},
    'dead_accounts_removed': 0,
    'started_at': datetime.now().isoformat()
}

ACCOUNTS_FILE = 'accounts.json'
SETTINGS_FILE = 'auto_add_settings.json'
STATS_FILE = 'stats.json'
WORKER_ADDS_FILE = 'worker_adds.json'
SERVER_ADMIN_FILE = 'server_admin.json'

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path) as f:
                c = f.read().strip()
                return json.loads(c) if c else default
    except:
        pass
    return default

def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_all():
    global accounts, auto_add_settings, stats, worker_adds, server_admin
    accounts = load_json(ACCOUNTS_FILE, [])
    auto_add_settings = load_json(SETTINGS_FILE, {})
    worker_adds = defaultdict(list, load_json(WORKER_ADDS_FILE, {}))
    server_admin = load_json(SERVER_ADMIN_FILE, {})
    
    loaded_stats = load_json(STATS_FILE, {
        'total_added': 0, 'today_added': 0,
        'verified_total': 0, 'verified_today': 0,
        'last_reset': datetime.now().strftime('%Y-%m-%d'),
        'last_verification': None,
        'daily_history': {},
        'worker_stats': {},
        'dead_accounts_removed': 0,
        'started_at': datetime.now().isoformat()
    })
    stats.update(loaded_stats)
    logger.info(f"Loaded: {len(accounts)} accounts, admin linked: {server_admin.get(str(SERVER_NUMBER), 'None')}")

load_all()

def run_async(coro):
    """Run async coroutine and return result"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def reset_daily():
    today = datetime.now().strftime('%Y-%m-%d')
    if stats.get('last_reset') != today:
        old = stats.get('last_reset', 'unknown')
        stats['daily_history'][old] = {
            'attempted': stats.get('today_added', 0),
            'verified': stats.get('verified_today', 0)
        }
        stats['today_added'] = 0
        stats['verified_today'] = 0
        stats['last_reset'] = today
        
        for wid in stats.get('worker_stats', {}):
            stats['worker_stats'][wid]['today'] = 0
            stats['worker_stats'][wid]['verified_today'] = 0
        
        save_json(STATS_FILE, stats)
        cleanup_old_worker_adds()

def cleanup_old_worker_adds():
    """Remove worker add records older than 7 days"""
    cutoff = datetime.now() - timedelta(days=7)
    for wid in list(worker_adds.keys()):
        worker_adds[wid] = [
            a for a in worker_adds[wid] 
            if isinstance(a.get('time', ''), str) and datetime.fromisoformat(a['time']) > cutoff
        ]
    save_json(WORKER_ADDS_FILE, dict(worker_adds))

def send_telegram(text):
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': REPORT_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=10
        )
    except:
        pass

def get_client(account_or_session):
    """Create TelegramClient from account dict or session string"""
    if isinstance(account_or_session, dict):
        session_str = account_or_session.get('session', '')
    else:
        session_str = account_or_session
    
    return TelegramClient(
        StringSession(session_str), API_ID, API_HASH,
        connection_retries=10, retry_delay=3, timeout=30,
        auto_reconnect=True
    )

def remove_dead_account(account_id, reason="Unknown"):
    """Remove a dead/unauthorized account"""
    global accounts
    acc_id_str = str(account_id)
    
    acc = next((a for a in accounts if a['id'] == account_id), None)
    acc_name = acc.get('name', str(account_id)) if acc else str(account_id)
    
    # Remove from all storages
    accounts = [a for a in accounts if a['id'] != account_id]
    auto_add_settings.pop(acc_id_str, None)
    running_tasks.pop(acc_id_str, None)
    worker_adds.pop(acc_id_str, None)
    
    if server_admin.get(str(SERVER_NUMBER)) == account_id:
        server_admin.pop(str(SERVER_NUMBER), None)
        save_json(SERVER_ADMIN_FILE, server_admin)
    
    save_json(ACCOUNTS_FILE, accounts)
    save_json(SETTINGS_FILE, auto_add_settings)
    save_json(WORKER_ADDS_FILE, dict(worker_adds))
    
    stats['dead_accounts_removed'] = stats.get('dead_accounts_removed', 0) + 1
    save_json(STATS_FILE, stats)
    
    logger.warning(f"🗑️ Removed dead account: {acc_name} (Reason: {reason})")
    send_telegram(f"⚠️ <b>{SERVER_NAME}</b>\n🗑️ Removed dead account: {acc_name}\n📋 Reason: {reason}")
    
    return acc_name

def check_account_auth(account):
    """Check if an account is still authorized"""
    async def check():
        client = get_client(account)
        await client.connect()
        try:
            return await client.is_user_authorized()
        except:
            return False
        finally:
            await client.disconnect()
    
    return run_async(check())

# ============================================
# VERIFICATION SYSTEM
# ============================================
def verify_worker_adds(admin_account, worker_ids):
    """Admin checks group and verifies which workers added which members"""
    if not admin_account:
        return None
    
    logger.info(f"🔍 Starting verification via admin: {admin_account.get('name')}")
    
    result = {}
    
    async def verify():
        client = get_client(admin_account)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                logger.error("Admin account not authorized")
                return result
            
            group = await client.get_entity(TARGET_GROUP)
            logger.info(f"📊 Fetching members from: {group.title}")
            
            all_members = []
            offset = 0
            while True:
                participants = await client(GetParticipantsRequest(
                    channel=group,
                    filter=ChannelParticipantsRecent(),
                    offset=offset,
                    limit=200,
                    hash=0
                ))
                if not participants.users:
                    break
                
                for user in participants.users:
                    if not user.bot:
                        all_members.append({
                            'id': user.id,
                            'name': (user.first_name or '') + (' ' + user.last_name if user.last_name else ''),
                            'username': user.username or '',
                            'phone': user.phone or ''
                        })
                
                offset += len(participants.users)
                if len(participants.users) < 200:
                    break
                time.sleep(2)
            
            logger.info(f"👥 Total members in group: {len(all_members)}")
            group_member_ids = {m['id'] for m in all_members}
            group_member_map = {m['id']: m for m in all_members}
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            for wid in worker_ids:
                wid_str = str(wid)
                if wid_str not in worker_adds:
                    result[wid] = {'verified_count': 0, 'members': [], 'attempted': 0}
                    continue
                
                adds = worker_adds[wid_str]
                today_adds = [a for a in adds if a.get('time', '').startswith(today)]
                
                verified_members = []
                for add in today_adds:
                    uid = add.get('user_id')
                    if uid and uid in group_member_ids:
                        verified_members.append({
                            'id': uid,
                            'name': group_member_map[uid]['name'],
                            'username': group_member_map[uid].get('username', ''),
                            'phone': add.get('phone', group_member_map[uid].get('phone', '')),
                            'added_at': add.get('time', '')
                        })
                
                result[wid] = {
                    'verified_count': len(verified_members),
                    'attempted': len(today_adds),
                    'members': verified_members,
                    'success_rate': round(len(verified_members) / len(today_adds) * 100, 1) if today_adds else 0
                }
                
                if 'worker_stats' not in stats:
                    stats['worker_stats'] = {}
                if wid_str not in stats['worker_stats']:
                    stats['worker_stats'][wid_str] = {'total': 0, 'today': 0, 'verified_total': 0, 'verified_today': 0}
                
                stats['worker_stats'][wid_str]['verified_today'] = len(verified_members)
                stats['worker_stats'][wid_str]['verified_total'] += len(verified_members)
                stats['verified_today'] = stats.get('verified_today', 0) + len(verified_members)
                stats['verified_total'] = stats.get('verified_total', 0) + len(verified_members)
            
            stats['last_verification'] = datetime.now().isoformat()
            save_json(STATS_FILE, stats)
            
            return result
            
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return result
        finally:
            await client.disconnect()
    
    return run_async(verify())

# ============================================
# SCRAPE MEMBERS
# ============================================
def scrape_group_members(loop, client, group_username, limit=300):
    """Scrape members from a group"""
    ids = set()
    try:
        entity = loop.run_until_complete(client.get_entity(group_username))
        participants = loop.run_until_complete(client.get_participants(entity, limit=limit))
        for user in participants:
            if user.id and not user.bot:
                ids.add(user.id)
        logger.info(f"👥 Scraped {group_username}: {len(ids)} members")
    except Exception as e:
        logger.debug(f"Scrape {group_username}: {e}")
    return ids

# ============================================
# AUTO-ADD ENGINE WITH TRACKING
# ============================================
def auto_add_worker(account):
    """Worker that adds members AND tracks who was added"""
    acc_id = account['id']
    acc_key = str(acc_id)
    session_str = account['session']
    attempted = set()
    joined = False
    cycle_count = 0
    
    if 'worker_stats' not in stats:
        stats['worker_stats'] = {}
    if acc_key not in stats['worker_stats']:
        stats['worker_stats'][acc_key] = {'total': 0, 'today': 0, 'verified_total': 0, 'verified_today': 0}
    
    logger.info(f"🔥 AUTO-ADD STARTED: {account.get('name')} -> @{TARGET_GROUP}")
    
    while True:
        try:
            settings = auto_add_settings.get(acc_key, {})
            if not settings.get('enabled', True):
                time.sleep(30)
                continue
            
            reset_daily()
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                client = TelegramClient(
                    StringSession(session_str), API_ID, API_HASH,
                    connection_retries=10, retry_delay=3, timeout=30
                )
                loop.run_until_complete(client.connect())
                
                if not loop.run_until_complete(client.is_user_authorized()):
                    logger.error(f"Account {acc_id} not authorized - removing")
                    loop.close()
                    remove_dead_account(acc_id, "Session unauthorized")
                    return  # Exit thread
                
                me = loop.run_until_complete(client.get_me())
                worker_phone = me.phone or account.get('phone', '')
                worker_name = (me.first_name or '') + (' ' + me.last_name if me.last_name else 'User')
                
                # Update account name
                account['name'] = worker_name
                account['phone'] = worker_phone
                save_json(ACCOUNTS_FILE, accounts)
                
                if not joined:
                    try:
                        grp = loop.run_until_complete(client.get_entity(TARGET_GROUP))
                        loop.run_until_complete(client(JoinChannelRequest(grp)))
                        joined = True
                        logger.info(f"✅ {worker_name} joined @{TARGET_GROUP}")
                    except Exception as e:
                        if 'already' in str(e).lower() or 'participant' in str(e).lower():
                            joined = True
                
                try:
                    group = loop.run_until_complete(client.get_entity(TARGET_GROUP))
                except:
                    loop.close()
                    time.sleep(120)
                    continue
                
                all_ids = set()
                
                try:
                    contacts = loop.run_until_complete(client(GetContactsRequest(0)))
                    for c in contacts.users:
                        if c.id and not c.bot:
                            all_ids.add(c.id)
                    logger.info(f"📱 Contacts: {len(all_ids)}")
                except Exception as e:
                    logger.error(f"Contacts error: {e}")
                
                try:
                    dialogs = loop.run_until_complete(client.get_dialogs(limit=500))
                    for d in dialogs:
                        if d.is_user and d.entity and d.entity.id and not d.entity.bot:
                            all_ids.add(d.entity.id)
                    logger.info(f"💬 With dialogs: {len(all_ids)}")
                except Exception as e:
                    logger.error(f"Dialogs error: {e}")
                
                source_groups = ['@telegram', '@durov', '@TelegramTips', '@contest', '@TelegramNews']
                for sg in source_groups:
                    try:
                        scraped = scrape_group_members(loop, client, sg, limit=200)
                        all_ids.update(scraped)
                    except:
                        pass
                
                logger.info(f"🔍 Total collected: {len(all_ids)}")
                
                fresh = list(all_ids - attempted)
                if not fresh or len(fresh) < 20:
                    attempted.clear()
                    fresh = list(all_ids)
                
                random.shuffle(fresh)
                
                cycle_count += 1
                added_this_cycle = 0
                delay = max(25, settings.get('delay_seconds', 25))
                
                logger.info(f"🔄 Cycle {cycle_count}: {len(fresh)} members to try")
                
                user_details = {}
                for uid in fresh[:300]:
                    try:
                        user = loop.run_until_complete(client.get_entity(uid))
                        user_details[uid] = {
                            'name': (user.first_name or '') + (' ' + user.last_name if user.last_name else ''),
                            'username': user.username or '',
                            'phone': getattr(user, 'phone', '') or ''
                        }
                    except:
                        user_details[uid] = {'name': '', 'username': '', 'phone': ''}
                
                for uid in fresh[:300]:
                    settings_check = auto_add_settings.get(acc_key, {})
                    if not settings_check.get('enabled', True):
                        break
                    
                    attempted.add(uid)
                    
                    try:
                        user_input = loop.run_until_complete(client.get_input_entity(uid))
                        loop.run_until_complete(client(InviteToChannelRequest(group, [user_input])))
                        
                        add_record = {
                            'user_id': uid,
                            'name': user_details.get(uid, {}).get('name', ''),
                            'phone': user_details.get(uid, {}).get('phone', ''),
                            'username': user_details.get(uid, {}).get('username', ''),
                            'time': datetime.now().isoformat(),
                            'added_by': worker_name,
                            'worker_id': acc_id
                        }
                        worker_adds[acc_key].append(add_record)
                        
                        stats['today_added'] = stats.get('today_added', 0) + 1
                        stats['total_added'] = stats.get('total_added', 0) + 1
                        if acc_key in stats.get('worker_stats', {}):
                            stats['worker_stats'][acc_key]['today'] = stats['worker_stats'][acc_key].get('today', 0) + 1
                            stats['worker_stats'][acc_key]['total'] = stats['worker_stats'][acc_key].get('total', 0) + 1
                        added_this_cycle += 1
                        
                        if added_this_cycle % 20 == 0:
                            save_json(STATS_FILE, stats)
                            save_json(WORKER_ADDS_FILE, dict(worker_adds))
                        
                        actual_delay = random.uniform(delay * 0.7, delay * 1.3)
                        time.sleep(actual_delay)
                        
                    except errors.FloodWaitError as e:
                        wait_time = e.seconds + random.randint(5, 15)
                        logger.warning(f"⏳ Flood {e.seconds}s, waiting {wait_time}s")
                        time.sleep(wait_time)
                    except (errors.UserPrivacyRestrictedError, errors.UserNotMutualContactError,
                            errors.UserAlreadyParticipantError, errors.UserKickedError,
                            errors.UserBannedInChannelError):
                        continue
                    except Exception as e:
                        continue
                
                logger.info(f"📊 Cycle {cycle_count}: +{added_this_cycle} | Today: {stats['today_added']} | Total: {stats['total_added']}")
                save_json(STATS_FILE, stats)
                save_json(WORKER_ADDS_FILE, dict(worker_adds))
                
                if added_this_cycle > 30:
                    send_telegram(
                        f"📊 <b>{SERVER_NAME}</b> - Worker: {worker_name}\n"
                        f"🔄 Cycle: {cycle_count}\n"
                        f"✅ Added: {added_this_cycle}\n"
                        f"📅 Today: {stats['today_added']:,}\n"
                        f"📊 Total: {stats['total_added']:,}"
                    )
                
            except errors.rpcerrorlist.AuthKeyUnregisteredError:
                logger.error(f"Auth key unregistered for account {acc_id}")
                loop.close()
                remove_dead_account(acc_id, "Auth key unregistered")
                return
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                try:
                    loop.run_until_complete(client.disconnect())
                except:
                    pass
                loop.close()
            
            rest = random.randint(120, 300)
            logger.info(f"😴 Rest {rest}s...")
            time.sleep(rest)
            
        except Exception as e:
            logger.error(f"Critical worker error: {e}")
            time.sleep(300)

def start_auto_add(account):
    """Start auto-add worker for an account"""
    acc_key = str(account['id'])
    if acc_key in running_tasks:
        return
    t = threading.Thread(target=auto_add_worker, args=(account,), daemon=True)
    t.start()
    running_tasks[acc_key] = t
    logger.info(f"🚀 Started worker for: {account.get('name', account['id'])}")

# ============================================
# FLASK ROUTES - PAGES
# ============================================
@app.route('/')
@app.route('/auto-add')
def index():
    if os.path.exists('auto_add.html'):
        return send_file('auto_add.html')
    return "auto_add.html not found"

@app.route('/login')
def login_page():
    if os.path.exists('login.html'):
        return send_file('login.html')
    return "login.html not found"

@app.route('/dashboard')
def dashboard():
    if os.path.exists('dashboard.html'):
        return send_file('dashboard.html')
    return send_file('auto_add.html')

@app.route('/dash')
def dash():
    if os.path.exists('dash.html'):
        return send_file('dash.html')
    return send_file('auto_add.html')

@app.route('/all')
def all_devices():
    if os.path.exists('all.html'):
        return send_file('all.html')
    return send_file('auto_add.html')

# ============================================
# FLASK ROUTES - API
# ============================================
@app.route('/ping')
@app.route('/api/health')
def health():
    reset_daily()
    admin_linked = str(server_admin.get(str(SERVER_NUMBER), '')) if server_admin.get(str(SERVER_NUMBER)) else None
    return jsonify({
        'status': 'ok',
        'server': SERVER_NAME,
        'number': SERVER_NUMBER,
        'accounts': len(accounts),
        'today_attempted': stats.get('today_added', 0),
        'today_verified': stats.get('verified_today', 0),
        'total_attempted': stats.get('total_added', 0),
        'total_verified': stats.get('verified_total', 0),
        'admin_linked': admin_linked,
        'dead_removed': stats.get('dead_accounts_removed', 0),
        'last_verification': stats.get('last_verification')
    })

@app.route('/api/public-stats')
def public_stats():
    reset_daily()
    return jsonify({
        'success': True,
        'stats': {
            'name': SERVER_NAME,
            'server_number': SERVER_NUMBER,
            'today_attempted': stats.get('today_added', 0),
            'today_verified': stats.get('verified_today', 0),
            'total_attempted': stats.get('total_added', 0),
            'total_verified': stats.get('verified_total', 0),
            'active_accounts': len(accounts),
            'target_group': TARGET_GROUP,
            'url': SERVER_URL,
            'last_verification': stats.get('last_verification')
        }
    })

@app.route('/api/server-info')
def server_info():
    admin_linked = server_admin.get(str(SERVER_NUMBER))
    return jsonify({
        'success': True,
        'server': {
            'number': SERVER_NUMBER,
            'name': SERVER_NAME,
            'url': SERVER_URL,
            'target_group': TARGET_GROUP,
            'total_servers': len(SERVERS),
            'other_servers': OTHER_SERVERS,
            'admin_linked': admin_linked
        }
    })

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        data = request.json
        phone = data.get('phone', '').strip()
        if not phone:
            return jsonify({'success': False, 'error': 'Phone required'})
        if not phone.startswith('+'):
            phone = '+' + phone
        
        async def send():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client.send_code_request(phone)
                sid = str(int(time.time()))
                temp_sessions[sid] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save()
                }
                return {'success': True, 'session_id': sid}
            except errors.FloodWaitError as e:
                return {'success': False, 'error': f'Wait {e.seconds}s'}
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '').strip()
        sid = data.get('session_id', '')
        pwd = data.get('password', '')
        
        if not sid or sid not in temp_sessions:
            return jsonify({'success': False, 'error': 'Session expired'})
        
        td = temp_sessions[sid]
        
        async def verify():
            client = TelegramClient(StringSession(td['session']), API_ID, API_HASH)
            await client.connect()
            try:
                try:
                    await client.sign_in(td['phone'], code, phone_code_hash=td['hash'])
                except errors.SessionPasswordNeededError:
                    if not pwd:
                        return {'need_password': True}
                    await client.sign_in(password=pwd)
                
                me = await client.get_me()
                new_id = int(time.time() * 1000)
                
                new_acc = {
                    'id': new_id,
                    'phone': me.phone or td['phone'],
                    'name': (me.first_name or '') + (' ' + me.last_name if me.last_name else 'User'),
                    'username': me.username or '',
                    'session': client.session.save(),
                    'active': True
                }
                accounts.append(new_acc)
                save_json(ACCOUNTS_FILE, accounts)
                
                auto_add_settings[str(new_id)] = {
                    'enabled': True,
                    'target_group': TARGET_GROUP,
                    'delay_seconds': 25,
                    'auto_join': True
                }
                save_json(SETTINGS_FILE, auto_add_settings)
                
                if 'worker_stats' not in stats:
                    stats['worker_stats'] = {}
                stats['worker_stats'][str(new_id)] = {
                    'total': 0, 'today': 0, 'verified_total': 0, 'verified_today': 0
                }
                save_json(STATS_FILE, stats)
                
                try:
                    grp = await client.get_entity(TARGET_GROUP)
                    await client(JoinChannelRequest(grp))
                except:
                    pass
                
                start_auto_add(new_acc)
                
                return {
                    'success': True,
                    'account': {'id': new_id, 'name': new_acc['name'], 'phone': new_acc['phone']},
                    'auto_add_started': True
                }
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired'}
            except errors.PasswordHashInvalidError:
                return {'success': False, 'error': 'Wrong password'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(verify())
        if sid in temp_sessions:
            del temp_sessions[sid]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/accounts')
def get_accounts():
    acc_list = []
    for a in accounts:
        aid_str = str(a['id'])
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        is_admin = server_admin.get(str(SERVER_NUMBER)) == a['id']
        acc_list.append({
            'id': a['id'],
            'name': a.get('name', '?'),
            'phone': a.get('phone', ''),
            'username': a.get('username', ''),
            'active': a.get('active', True),
            'auto_add_enabled': auto_add_settings.get(aid_str, {}).get('enabled', True),
            'is_admin': is_admin,
            'is_server_admin': is_admin,
            'stats': {
                'total_attempted': ws.get('total', 0),
                'today_attempted': ws.get('today', 0),
                'total_verified': ws.get('verified_total', 0),
                'today_verified': ws.get('verified_today', 0)
            }
        })
    return jsonify({'success': True, 'accounts': acc_list})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    global accounts
    aid = request.json.get('accountId')
    name = remove_dead_account(aid, "Manual removal")
    return jsonify({'success': True, 'message': f'Removed: {name}'})

# ============================================
# FIXED: GET MESSAGES / CHATS - COMPLETELY REWRITTEN
# ============================================
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats (dialogs) and messages for dashboard - FULLY FIXED"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
            
        aid = data.get('accountId')
        if not aid:
            return jsonify({'success': False, 'error': 'Account ID is required'})
            
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found in storage'})
        
        logger.info(f"📱 Fetching chats for account: {acc.get('name', 'Unknown')} (ID: {aid})")
        
        async def fetch():
            client = get_client(acc)
            try:
                await client.connect()
                
                # Check authorization
                try:
                    is_auth = await client.is_user_authorized()
                except errors.rpcerrorlist.AuthKeyUnregisteredError:
                    await client.disconnect()
                    remove_dead_account(aid, "Auth key unregistered")
                    return {'success': False, 'error': 'auth_key_unregistered', 'message': 'Session expired. Please remove and re-add this account.'}
                except Exception as e:
                    await client.disconnect()
                    logger.error(f"Auth check error: {e}")
                    return {'success': False, 'error': 'connection_error', 'message': f'Connection error: {str(e)[:100]}'}
                
                if not is_auth:
                    await client.disconnect()
                    remove_dead_account(aid, "Session unauthorized")
                    return {'success': False, 'error': 'auth_key_unregistered', 'message': 'Account not authorized. Please re-add this account.'}
                
                # Fetch dialogs
                logger.info(f"Fetching dialogs for {acc.get('name')}...")
                try:
                    dialogs = await client.get_dialogs(limit=100)
                    logger.info(f"Got {len(dialogs)} dialogs")
                except Exception as e:
                    logger.error(f"Get dialogs error: {e}")
                    await client.disconnect()
                    return {'success': False, 'error': 'dialogs_error', 'message': f'Failed to load dialogs: {str(e)[:100]}'}
                
                chats_list = []
                all_messages = []
                
                for dialog in dialogs:
                    try:
                        # Get chat ID as string
                        chat_id = str(dialog.id)
                        
                        # Determine chat type
                        chat_type = 'user'
                        title = dialog.name or 'Unknown'
                        
                        if dialog.is_group:
                            chat_type = 'group'
                        elif dialog.is_channel:
                            chat_type = 'channel'
                        
                        # Check if bot
                        entity = dialog.entity
                        if hasattr(entity, 'bot') and entity.bot:
                            chat_type = 'bot'
                        
                        # Get last message info
                        last_msg_text = ''
                        last_msg_date = 0
                        last_msg_media = None
                        
                        if dialog.message:
                            last_msg_text = (dialog.message.message or '')[:200]
                            last_msg_date = dialog.message.date.timestamp() if dialog.message.date else 0
                            
                            if dialog.message.media:
                                if hasattr(dialog.message.media, 'photo'):
                                    last_msg_media = 'photo'
                                elif hasattr(dialog.message.media, 'document'):
                                    last_msg_media = 'document'
                                elif hasattr(dialog.message.media, 'webpage'):
                                    last_msg_media = 'link'
                        
                        chats_list.append({
                            'id': chat_id,
                            'title': title,
                            'type': chat_type,
                            'unread': dialog.unread_count or 0,
                            'lastMessage': last_msg_text,
                            'lastMessageDate': last_msg_date,
                            'lastMessageMedia': last_msg_media
                        })
                        
                        # Fetch recent messages (limit to 15 per chat to prevent timeouts)
                        try:
                            messages = await client.get_messages(entity, limit=15)
                            for msg in messages:
                                if not msg.message and not msg.media:
                                    continue
                                
                                media_type = None
                                has_media = False
                                
                                if msg.media:
                                    has_media = True
                                    if hasattr(msg.media, 'photo'):
                                        media_type = 'photo'
                                    elif hasattr(msg.media, 'document'):
                                        media_type = 'document'
                                    elif hasattr(msg.media, 'webpage'):
                                        media_type = 'link'
                                    else:
                                        media_type = 'media'
                                
                                all_messages.append({
                                    'chatId': chat_id,
                                    'id': msg.id,
                                    'text': msg.message or '',
                                    'date': msg.date.timestamp() if msg.date else 0,
                                    'out': msg.out,
                                    'hasMedia': has_media,
                                    'mediaType': media_type
                                })
                        except Exception as e:
                            logger.debug(f"Messages fetch error for {title}: {e}")
                            # Don't fail the whole request if one chat fails
                            pass
                        
                    except Exception as e:
                        logger.debug(f"Dialog processing error: {e}")
                        continue
                
                logger.info(f"📱 Successfully loaded {len(chats_list)} chats and {len(all_messages)} messages for {acc.get('name')}")
                
                return {
                    'success': True,
                    'chats': chats_list,
                    'messages': all_messages,
                    'account_name': acc.get('name', 'Unknown'),
                    'chat_count': len(chats_list),
                    'message_count': len(all_messages)
                }
                
            except Exception as e:
                logger.error(f"Get messages outer error: {e}")
                return {'success': False, 'error': 'server_error', 'message': f'Error: {str(e)[:100]}'}
            finally:
                try:
                    await client.disconnect()
                except:
                    pass
        
        result = run_async(fetch())
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API get-messages error: {e}")
        return jsonify({'success': False, 'error': 'api_error', 'message': str(e)[:100]})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send a message from an account"""
    try:
        data = request.json
        aid = data.get('accountId')
        chat_id = data.get('chatId')
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message required'})
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = get_client(acc)
            await client.connect()
            try:
                # Parse chat_id - try different peer types
                try:
                    chat_id_int = int(chat_id)
                    # Try peer types sequentially
                    entity = None
                    for PeerClass in [PeerUser, PeerChat, PeerChannel]:
                        try:
                            entity = await client.get_entity(PeerClass(chat_id_int))
                            break
                        except:
                            continue
                    if not entity:
                        entity = await client.get_entity(chat_id)
                except:
                    entity = await client.get_entity(chat_id)
                
                await client.send_message(entity, message)
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

# ============================================
# ADMIN LINKING ROUTES
# ============================================
@app.route('/api/link-admin', methods=['POST'])
def link_admin():
    """Link an account as the admin checker for this server"""
    data = request.json
    admin_id = data.get('accountId')
    
    if not admin_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    acc = next((a for a in accounts if a['id'] == admin_id), None)
    if not acc:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def check_admin():
        client = get_client(acc)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return False, 'Account not authorized'
            
            group = await client.get_entity(TARGET_GROUP)
            
            try:
                participant = await client(functions.channels.GetParticipantRequest(group, 'me'))
                is_admin = hasattr(participant.participant, 'admin_rights') and participant.participant.admin_rights
                
                if not is_admin:
                    return False, 'Account is NOT an admin of the target group'
                
                return True, 'Admin verified successfully'
            except Exception as e:
                return False, f'Cannot verify admin: {str(e)[:100]}'
        finally:
            await client.disconnect()
    
    result = run_async(check_admin())
    
    if result[0]:
        server_admin[str(SERVER_NUMBER)] = admin_id
        save_json(SERVER_ADMIN_FILE, server_admin)
        
        auto_add_settings[str(admin_id)] = auto_add_settings.get(str(admin_id), {})
        auto_add_settings[str(admin_id)]['is_server_admin'] = True
        save_json(SETTINGS_FILE, auto_add_settings)
        
        logger.info(f"🔗 Admin linked: {acc['name']} -> Server {SERVER_NAME}")
        send_telegram(f"🔗 <b>{SERVER_NAME}</b>\n👑 Admin linked: {acc['name']}")
        return jsonify({'success': True, 'message': f'Admin linked: {acc["name"]}', 'admin_name': acc['name']})
    
    return jsonify({'success': False, 'error': result[1]})

@app.route('/api/unlink-admin', methods=['POST'])
def unlink_admin():
    server_admin.pop(str(SERVER_NUMBER), None)
    save_json(SERVER_ADMIN_FILE, server_admin)
    return jsonify({'success': True, 'message': 'Admin unlinked'})

@app.route('/api/admin-status')
def admin_status():
    admin_id = server_admin.get(str(SERVER_NUMBER))
    if admin_id:
        acc = next((a for a in accounts if a['id'] == admin_id), None)
        return jsonify({
            'success': True,
            'linked': True,
            'admin': {
                'id': admin_id,
                'name': acc['name'] if acc else 'Unknown',
                'phone': acc['phone'] if acc else ''
            } if acc else None
        })
    return jsonify({'success': True, 'linked': False, 'admin': None})

# ============================================
# VERIFICATION ROUTES
# ============================================
@app.route('/api/verify-adds', methods=['POST'])
def trigger_verification():
    """Trigger admin verification of worker adds"""
    admin_id = server_admin.get(str(SERVER_NUMBER))
    
    if not admin_id:
        return jsonify({'success': False, 'error': 'No admin account linked'})
    
    admin_acc = next((a for a in accounts if a['id'] == admin_id), None)
    if not admin_acc:
        return jsonify({'success': False, 'error': 'Admin account not found'})
    
    worker_ids = [a['id'] for a in accounts if a['id'] != admin_id]
    
    if not worker_ids:
        return jsonify({'success': False, 'error': 'No worker accounts'})
    
    result = verify_worker_adds(admin_acc, worker_ids)
    
    if result is None:
        return jsonify({'success': False, 'error': 'Verification failed'})
    
    total_verified = sum(r.get('verified_count', 0) for r in result.values())
    total_attempted = sum(r.get('attempted', 0) for r in result.values())
    
    workers_detail = []
    for wid, data in result.items():
        acc = next((a for a in accounts if a['id'] == wid), None)
        workers_detail.append({
            'id': wid,
            'name': acc['name'] if acc else str(wid),
            'verified': data.get('verified_count', 0),
            'attempted': data.get('attempted', 0),
            'success_rate': data.get('success_rate', 0)
        })
    
    workers_detail.sort(key=lambda x: x['verified'], reverse=True)
    
    return jsonify({
        'success': True,
        'verification_time': stats.get('last_verification'),
        'summary': {
            'total_verified': total_verified,
            'total_attempted': total_attempted,
            'success_rate': round(total_verified / total_attempted * 100, 1) if total_attempted else 0
        },
        'workers': workers_detail
    })

@app.route('/api/verified-stats')
def verified_stats():
    reset_daily()
    
    workers_detail = []
    for a in accounts:
        aid_str = str(a['id'])
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        workers_detail.append({
            'id': a['id'],
            'name': a.get('name', '?'),
            'total_attempted': ws.get('total', 0),
            'today_attempted': ws.get('today', 0),
            'total_verified': ws.get('verified_total', 0),
            'today_verified': ws.get('verified_today', 0),
            'is_admin': server_admin.get(str(SERVER_NUMBER)) == a['id']
        })
    
    workers_detail.sort(key=lambda x: x['today_verified'], reverse=True)
    
    return jsonify({
        'success': True,
        'server': SERVER_NAME,
        'server_number': SERVER_NUMBER,
        'today_verified': stats.get('verified_today', 0),
        'total_verified': stats.get('verified_total', 0),
        'today_attempted': stats.get('today_added', 0),
        'total_attempted': stats.get('total_added', 0),
        'last_verification': stats.get('last_verification'),
        'admin_linked': server_admin.get(str(SERVER_NUMBER)),
        'workers': workers_detail
    })

# ============================================
# REMAINING ROUTES (auto-add settings, test, join, sessions, ranking, report)
# ============================================
@app.route('/api/auto-add-settings', methods=['GET', 'POST'])
def auto_add_settings_route():
    if request.method == 'GET':
        aid = request.args.get('accountId')
        aid_str = str(aid)
        s = auto_add_settings.get(aid_str, {
            'enabled': False, 'target_group': TARGET_GROUP, 'delay_seconds': 25, 'auto_join': True
        })
        s['account_id'] = aid
        s['added_today'] = stats.get('today_added', 0)
        s['total_added'] = stats.get('total_added', 0)
        s['verified_today'] = stats.get('verified_today', 0)
        s['verified_total'] = stats.get('verified_total', 0)
        s['server_name'] = SERVER_NAME
        s['server_number'] = SERVER_NUMBER
        s['is_admin'] = server_admin.get(str(SERVER_NUMBER)) == aid
        s['server_admin_id'] = server_admin.get(str(SERVER_NUMBER))
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        s['worker_stats'] = ws
        return jsonify({'success': True, 'settings': s})
    
    data = request.json
    aid = data.get('accountId')
    akey = str(aid)
    
    was_on = auto_add_settings.get(akey, {}).get('enabled', False)
    auto_add_settings[akey] = {
        'enabled': data.get('enabled', False),
        'target_group': data.get('target_group', TARGET_GROUP),
        'delay_seconds': max(25, data.get('delay_seconds', 25)),
        'auto_join': True,
        'last_updated': datetime.now().isoformat()
    }
    
    if server_admin.get(str(SERVER_NUMBER)) == aid:
        auto_add_settings[akey]['is_server_admin'] = True
    
    save_json(SETTINGS_FILE, auto_add_settings)
    
    if data.get('enabled') and not was_on:
        acc = next((a for a in accounts if a['id'] == aid), None)
        if acc:
            start_auto_add(acc)
    
    return jsonify({'success': True, 'message': 'Settings saved'})

@app.route('/api/auto-add-stats')
def auto_add_stats():
    reset_daily()
    aid = request.args.get('accountId')
    aid_str = str(aid) if aid else None
    ws = stats.get('worker_stats', {}).get(aid_str, {}) if aid_str else {}
    
    return jsonify({
        'success': True,
        'added_today': stats.get('today_added', 0),
        'total_added': stats.get('total_added', 0),
        'verified_today': stats.get('verified_today', 0),
        'verified_total': stats.get('verified_total', 0),
        'server_name': SERVER_NAME,
        'server_number': SERVER_NUMBER,
        'worker_stats': ws
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def test():
            client = get_client(acc)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Not authorized'}
                
                group_found = False
                group_title = TARGET_GROUP
                member_count = 0
                try:
                    grp = await client.get_entity(TARGET_GROUP)
                    group_found = True
                    group_title = getattr(grp, 'title', TARGET_GROUP)
                    participants = await client(GetParticipantsRequest(
                        channel=grp, filter=ChannelParticipantsRecent(),
                        offset=0, limit=1, hash=0
                    ))
                    member_count = participants.count if hasattr(participants, 'count') else len(participants.users)
                except:
                    pass
                
                available = 0
                try:
                    contacts = await client(GetContactsRequest(0))
                    available += len([c for c in contacts.users if not c.bot])
                except:
                    pass
                try:
                    dialogs = await client.get_dialogs(limit=200)
                    available += len([d for d in dialogs if d.is_user and not d.entity.bot])
                except:
                    pass
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'group_members': member_count,
                    'available_members': available,
                    'target_group': TARGET_GROUP
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(test()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/join-group', methods=['POST'])
def join_group():
    try:
        aid = request.json.get('accountId')
        grp = request.json.get('group', TARGET_GROUP)
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Not found'})
        
        async def join():
            client = get_client(acc)
            await client.connect()
            try:
                entity = await client.get_entity(grp)
                await client(JoinChannelRequest(entity))
                return {'success': True, 'message': f'Joined {grp}'}
            except Exception as e:
                if 'already' in str(e).lower():
                    return {'success': True, 'message': 'Already member'}
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(join()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

# ============================================
# DEVICE/SESSION MANAGEMENT
# ============================================
@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    try:
        data = request.json
        aid = data.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = get_client(acc)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'fresh_reset_forbidden'}
                
                result = await client(functions.account.GetAuthorizationsRequest())
                current_hash = None
                sessions = []
                
                for auth in result.authorizations:
                    session_info = {
                        'hash': str(auth.hash),
                        'device_model': auth.device_model or 'Unknown',
                        'platform': auth.platform or 'Unknown',
                        'system_version': auth.system_version or '',
                        'app_name': auth.app_name or '',
                        'app_version': auth.app_version or '',
                        'date_created': auth.date_created.timestamp() if auth.date_created else 0,
                        'date_active': auth.date_active.timestamp() if auth.date_active else 0,
                        'ip': auth.ip or 'Unknown',
                        'country': auth.country or 'Unknown',
                        'region': auth.region or '',
                        'current': auth.current
                    }
                    if auth.current:
                        current_hash = str(auth.hash)
                    sessions.append(session_info)
                
                return {'success': True, 'sessions': sessions, 'current_hash': current_hash}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    try:
        data = request.json
        aid = data.get('accountId')
        hash_to_terminate = data.get('hash')
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = get_client(acc)
            await client.connect()
            try:
                await client(functions.account.ResetAuthorizationRequest(hash=int(hash_to_terminate)))
                return {'success': True, 'message': 'Session terminated'}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(terminate()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    try:
        data = request.json
        aid = data.get('accountId')
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = get_client(acc)
            await client.connect()
            try:
                result = await client(functions.account.GetAuthorizationsRequest())
                terminated = 0
                for auth in result.authorizations:
                    if not auth.current:
                        try:
                            await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
                            terminated += 1
                        except:
                            pass
                
                return {'success': True, 'message': f'Terminated {terminated} sessions'}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(terminate()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

# ============================================
# RANKING & REPORT
# ============================================
@app.route('/api/ranking')
def ranking():
    reset_daily()
    
    our_stats = {
        'name': SERVER_NAME,
        'number': SERVER_NUMBER,
        'today_attempted': stats.get('today_added', 0),
        'today_verified': stats.get('verified_today', 0),
        'total_attempted': stats.get('total_added', 0),
        'total_verified': stats.get('verified_total', 0),
        'active_workers': len(accounts),
        'admin_linked': server_admin.get(str(SERVER_NUMBER)) is not None,
        'url': SERVER_URL
    }
    
    all_stats = [our_stats]
    
    for srv in OTHER_SERVERS:
        try:
            r = requests.get(f"{srv['url']}/api/public-stats", timeout=10)
            if r.status_code == 200:
                d = r.json()
                if d.get('success'):
                    all_stats.append({
                        'name': srv['name'],
                        'number': srv['num'],
                        'today_attempted': d['stats'].get('today_attempted', 0),
                        'today_verified': d['stats'].get('today_verified', 0),
                        'total_attempted': d['stats'].get('total_attempted', 0),
                        'total_verified': d['stats'].get('total_verified', 0),
                        'active_workers': d['stats'].get('active_accounts', 0),
                        'url': srv['url']
                    })
                    continue
        except:
            pass
        all_stats.append({
            'name': srv['name'],
            'number': srv['num'],
            'today_attempted': 0,
            'today_verified': 0,
            'total_attempted': 0,
            'total_verified': 0,
            'offline': True,
            'url': srv['url']
        })
    
    all_stats.sort(key=lambda x: (x.get('today_verified', 0), x.get('today_attempted', 0)), reverse=True)
    
    total_verified_today = sum(s.get('today_verified', 0) for s in all_stats)
    total_attempted_today = sum(s.get('today_attempted', 0) for s in all_stats)
    
    return jsonify({
        'success': True,
        'rankings': all_stats,
        'summary': {
            'total_verified_today': total_verified_today,
            'total_attempted_today': total_attempted_today,
            'active_servers': len([s for s in all_stats if not s.get('offline')]),
            'total_servers': len(all_stats)
        }
    })

@app.route('/api/send-report')
def send_report():
    reset_daily()
    
    resp = ranking()
    data = resp.get_json()
    rankings = data.get('rankings', [])
    summary = data.get('summary', {})
    
    report = f"""
📊 <b>DAILY AUTO-ADD REPORT</b>
📅 <b>{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</b>
━━━━━━━━━━━━━━━━━━━━━━
🏆 <b>RANKINGS (Verified)</b>
━━━━━━━━━━━━━━━━━━━━━━
"""
    
    medals = ['🥇', '🥈', '🥉']
    for i, s in enumerate(rankings):
        medal = medals[i] if i < 3 else f'{i+1}️⃣'
        status = '⚠️ OFFLINE' if s.get('offline') else '✅ ONLINE'
        verified = s.get('today_verified', 0)
        attempted = s.get('today_attempted', 0)
        rate = round(verified / attempted * 100, 1) if attempted > 0 else 0
        
        bar_len = max(1, int(verified / max(summary.get('total_verified_today', 1), 1) * 20))
        bar = '█' * bar_len + '░' * (20 - bar_len)
        
        report += f"""
{medal} <b>{s['name']}</b> [{status}]
   {bar} <b>{verified:,}</b> ({rate}%)
"""
    
    report += f"""
━━━━━━━━━━━━━━━━━━━━━━
✅ Verified Today: <b>{summary.get('total_verified_today', 0):,}</b>
📥 Attempted: <b>{summary.get('total_attempted_today', 0):,}</b>
🌐 Active: <b>{summary.get('active_servers', 0)}/{summary.get('total_servers', 0)}</b>
━━━━━━━━━━━━━━━━━━━━━━
🖥️ <b>{SERVER_NAME}</b> #{SERVER_NUMBER}
"""
    
    send_telegram(report)
    
    return jsonify({'success': True, 'message': 'Report sent'})

# ============================================
# KEEP ALIVE & SCHEDULERS
# ============================================
def keep_alive():
    while True:
        time.sleep(240)
        try:
            requests.get(f"{SERVER_URL}/ping", timeout=10)
        except:
            pass

def dead_account_checker():
    """Periodically check all accounts and remove dead ones"""
    while True:
        time.sleep(600)  # Every 10 minutes
        for acc in list(accounts):
            try:
                is_auth = check_account_auth(acc)
                if not is_auth:
                    remove_dead_account(acc['id'], "Periodic auth check failed")
                time.sleep(3)
            except Exception as e:
                logger.debug(f"Health check error: {e}")

def daily_report_scheduler():
    last = None
    while True:
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        if now.hour in [0, 1] and last != today:
            time.sleep(random.randint(0, 1800))
            reset_daily()
            
            admin_id = server_admin.get(str(SERVER_NUMBER))
            if admin_id:
                admin_acc = next((a for a in accounts if a['id'] == admin_id), None)
                if admin_acc:
                    worker_ids = [a['id'] for a in accounts if a['id'] != admin_id]
                    verify_worker_adds(admin_acc, worker_ids)
            
            try:
                requests.get(f"{SERVER_URL}/api/send-report", timeout=30)
            except:
                pass
            last = today
        time.sleep(300)

def auto_verify_scheduler():
    while True:
        time.sleep(14400)
        try:
            admin_id = server_admin.get(str(SERVER_NUMBER))
            if admin_id:
                admin_acc = next((a for a in accounts if a['id'] == admin_id), None)
                if admin_acc:
                    worker_ids = [a['id'] for a in accounts if a['id'] != admin_id]
                    verify_worker_adds(admin_acc, worker_ids)
                    logger.info("Auto-verification completed")
        except Exception as e:
            logger.error(f"Auto-verify error: {e}")

def restore_and_start():
    time.sleep(5)
    for acc in list(accounts):
        if acc.get('session'):
            # Check auth before starting
            if check_account_auth(acc):
                start_auto_add(acc)
            else:
                remove_dead_account(acc['id'], "Failed auth check on startup")
            time.sleep(2)
    logger.info(f"🚀 All accounts processed")

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════════╗
║  AUTO-ADD SERVER #{SERVER_NUMBER}                    ║
║  Name: {SERVER_NAME}                             ║
║  Target: @{TARGET_GROUP}                ║
║  Mode: VERIFIED TRACKING             ║
║  Port: {PORT}                           ║
║  Admin: {'Linked' if server_admin.get(str(SERVER_NUMBER)) else 'Not linked'}           ║
║  Dead Check: Every 10 min            ║
╚══════════════════════════════════════╝
    """)
    
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=daily_report_scheduler, daemon=True).start()
    threading.Thread(target=auto_verify_scheduler, daemon=True).start()
    threading.Thread(target=dead_account_checker, daemon=True).start()
    threading.Thread(target=restore_and_start, daemon=True).start()
    
    send_telegram(
        f"🟢 <b>{SERVER_NAME}</b> Online!\n"
        f"📋 Server #{SERVER_NUMBER}\n"
        f"🎯 @{TARGET_GROUP}\n"
        f"🔍 Verified Tracking\n"
        f"🗑️ Auto-remove dead accounts\n"
        f"👑 Admin: {'Linked ✅' if server_admin.get(str(SERVER_NUMBER)) else 'Not linked ❌'}"
    )
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
