#!/usr/bin/env python
# IRC Football - Developed by acidvegas in Python (https://git.acid.vegas/ircfootball)

'''
Commands:
	@football        | Information about the bot
	@football help   | Show the list of commands
	@football scores | Top 10 players by touchdowns
	@football triggers | Client triggers to auto dodge, intercept & pick up the football
	!dodge           | 1 in 3 chance to evade a tackle, only in the 3 seconds after one connects
	!football        | Pick up the football or see who has it
	!intercept       | 1 in 20 chance to steal the football within 30 seconds of a pass
	!pass <nick>     | Pass the football to someone (1 in 20 chance it is incomplete)
	!tackle <nick>   | Tackle the holder to make them fumble, or anyone else to bench them (once every 5 minutes)

Hold the football for 24 hours to score a touchdown. Every day you keep it scores another one,
but each day also makes you easier to tackle (1 in 10, then 1 in 9, and so on down to 1 in 3).
'''

import asyncio
import json
import os
import random
import secrets
import ssl
import time

# Connection
server     = 'irc.supernets.org'
port       = 6697
use_ipv6   = False
use_ssl    = True
vhost      = None
channel    = '#superbowl'
key        = None

# Identity
nickname = 'FOOTBALL'
username = 'FOOTB'
realname = 'PLAY BALL'

# Login
nickserv_password = None # left empty on purpose, the bot registers itself and saves the password to password_file
network_password  = None
operator_name     = 'football'
operator_password = None

# Settings
user_modes       = 'BdDg' # +d requires additional ! and @ to be in your set::channel-command-prefix on UnrealIRCd
state_file       = 'football.json'
password_file    = 'football_password.txt'
register_delay   = 7200 # seconds to wait before registering the nick, the network delays new registrations
football_blocked = ('acid_radio','aibird','cancer','dealer','druqs','elimanning','events','football','fuckyou','gitea','guru','hardchats','irccex','jeffreygrepstein','link','polls','pyylmeaux','scroll','taskbot','uselessbot') # lowercase bot nicks from https://git.supernets.org/ircart/ircart (supernets/bots.txt)

# Formatting Control Characters / Color Codes
bold        = '\x02'
italic      = '\x1D'
underline   = '\x1F'
reverse     = '\x16'
reset       = '\x0f'
white       = '00'
black       = '01'
blue        = '02'
green       = '03'
red         = '04'
brown       = '05'
purple      = '06'
orange      = '07'
yellow      = '08'
light_green = '09'
cyan        = '10'
light_cyan  = '11'
light_blue  = '12'
pink        = '13'
grey        = '14'
light_grey  = '15'

def color(msg, foreground, background=None):
	return f'\x03{foreground},{background}{msg}{reset}' if background else f'\x03{foreground}{msg}{reset}'

def debug(data):
	print('{0} | [~] - {1}'.format(time.strftime('%I:%M:%S'), data))

def error(data, reason=None):
	print('{0} | [!] - {1} ({2})'.format(time.strftime('%I:%M:%S'), data, str(reason))) if reason else print('{0} | [!] - {1}'.format(time.strftime('%I:%M:%S'), data))

def human(seconds):
	weeks, days = divmod(int(seconds//86400), 7)
	if weeks and days:
		return f'{weeks}w {days}d'
	elif weeks:
		return f'{weeks}w'
	elif days:
		return f'{days}d'
	return '{0}h'.format(int(seconds//3600))

def luck(odds):
	return True if random.randint(1,odds) == 1 else False

def ordinal(number):
	return '{0}{1}'.format(number, 'th' if number % 100 in (11,12,13) else {1:'st',2:'nd',3:'rd'}.get(number % 10, 'th'))

def ssl_ctx():
	ctx = ssl.create_default_context()
	ctx.check_hostname = False
	ctx.verify_mode = ssl.CERT_NONE
	return ctx

class Bot():
	def __init__(self):
		self.members     = dict() # lowercase nick -> nick
		self.ball        = None   # nick holding the football
		self.ball_since  = 0      # when the holder picked it up
		self.ball_scores = 0      # touchdowns scored during this hold
		self.ball_pass   = None   # {'passer':nick,'time':time} for the !intercept window
		self.benched     = dict() # lowercase nick -> time they can play again
		self.tackles     = dict() # lowercase nick -> time of their last tackle attempt
		self.dodge       = None   # {'holder':nick,'tackler':nick,'time':time} while the 3 second !dodge window is open
		self.players     = dict() # lowercase nick -> {'nick':nick,'touchdowns':int,'longest':seconds}
		self.passes      = 0
		self.intercepts  = 0
		self.pending     = None   # password of a nick registration we are waiting on
		self.loops       = {'dodge':None,'register':None,'touchdowns':None}
		self.reader      = None
		self.writer      = None

	def load(self):
		if os.path.isfile(state_file):
			with open(state_file) as state:
				data             = json.loads(state.read())
				self.ball        = data['ball']
				self.ball_since  = data['ball_since']
				self.ball_scores = data['ball_scores']
				self.benched     = data['benched']
				self.players     = data['players']
				self.passes      = data['passes']
				self.intercepts  = data['intercepts']
				debug('reloaded state')

	def save(self):
		with open(state_file, 'w') as state:
			json.dump({'ball':self.ball, 'ball_since':self.ball_since, 'ball_scores':self.ball_scores, 'benched':self.benched, 'players':self.players, 'passes':self.passes, 'intercepts':self.intercepts}, state)

	def player(self, nick):
		return self.players.setdefault(nick.lower(), {'nick':nick, 'touchdowns':0, 'longest':0})

	def playable(self, nick):
		return nick.lower() not in football_blocked and self.benched.get(nick.lower(), 0) <= time.time()

	def odds(self):
		return max(3, 10-self.ball_scores)

	async def raw(self, data):
		self.writer.write(data[:510].encode('utf-8') + b'\r\n')
		await self.writer.drain()

	async def action(self, chan, msg):
		await self.sendmsg(chan, f'\x01ACTION {msg}\x01')

	async def sendmsg(self, target, msg):
		await self.raw(f'PRIVMSG {target} :{msg}')

	async def notice(self, target, msg):
		await self.raw(f'NOTICE {target} :{msg}')

	async def connect(self):
		self.load()
		while True:
			try:
				options = {
					'host'       : server,
					'port'       : port,
					'limit'      : 1024,
					'ssl'        : ssl_ctx() if use_ssl else None,
					'family'     : 10 if use_ipv6 else 2,
					'local_addr' : vhost
				}
				self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(**options), 15)
				await self.raw(f'USER {username} 0 * :{realname}')
				await self.raw('NICK ' + nickname)
			except Exception as ex:
				error('error: failed to connect to ' + server, ex)
			else:
				await self.listen()
				for loop in self.loops:
					if self.loops[loop]:
						self.loops[loop].cancel()
				self.members = dict()
				self.pending = None
				self.ball_pass = None
			finally:
				await asyncio.sleep(30)

	async def loop_register(self):
		await asyncio.sleep(register_delay)
		try:
			self.pending = secrets.token_urlsafe(18)
			await self.sendmsg('NickServ', f'REGISTER {self.pending}')
			debug('sent a nick registration to NickServ')
		except Exception as ex:
			error('error: loop_register failed', ex)

	async def loop_touchdowns(self):
		while True:
			try:
				self.benched = {nick:until for nick, until in self.benched.items() if until > time.time()}
				if self.ball:
					scored = int((time.time()-self.ball_since)//86400)
					if scored > self.ball_scores:
						player = self.player(self.ball)
						player['touchdowns'] += scored - self.ball_scores # more than one if the bot was down for a few days
						self.ball_scores = scored
						player['longest'] = max(player['longest'], time.time()-self.ball_since)
						self.save()
						await self.action(channel, '{0} {1} {2}'.format(color(self.ball, cyan), color('scores a TOUCHDOWN! 🏈', yellow), color('({0}, holding {1})'.format(ordinal(player['touchdowns']), human(time.time()-self.ball_since)), grey)))
			except Exception as ex:
				error('error: loop_touchdowns failed', ex)
			finally:
				await asyncio.sleep(60)

	async def fumble(self, nick):
		if self.ball and nick.lower() == self.ball.lower():
			player = self.player(self.ball)
			player['longest'] = max(player['longest'], time.time()-self.ball_since)
			self.ball        = None
			self.ball_scores = 0
			self.ball_pass   = None
			self.dodge       = None
			self.save()
			await self.action(channel, '{0} {1}'.format(color(nick, cyan), color('fumbled the 🏈', yellow)))

	async def loop_dodge(self, nick, tackler):
		await asyncio.sleep(3)
		try:
			if self.dodge and self.dodge['holder'] == nick:
				await self.down(nick, tackler)
		except Exception as ex:
			error('error: loop_dodge failed', ex)

	async def down(self, nick, tackler):
		self.dodge = None
		await self.action(channel, '{0} {1}'.format(color(nick, cyan), color('is dragged down!', yellow)))
		await self.fumble(nick)
		if luck(5):
			await self.bench(nick)
			await self.action(channel, '{0} {1}'.format(color(nick, cyan), color('is carted off the field for an hour.', yellow)))
		if luck(100):
			await self.raw(f'KICK {channel} {nick} :{nick} GOT CTE AND IS MADE FUCKING RETARDED')

	async def bench(self, nick):
		self.benched[nick.lower()] = time.time() + 3600
		self.save()

	async def scores(self, chan):
		rows = sorted(self.players.values(), key=lambda player: player['touchdowns'], reverse=True)
		rows = [player for player in rows if player['touchdowns']][:10]
		if not rows:
			await self.sendmsg(chan, 'nobody has scored a touchdown yet, pick up the 🏈 and hold it for 24 hours')
			return
		rank  = len(str(len(rows)))
		names = max(len(player['nick']) for player in rows)
		await self.sendmsg(chan, color('{0} {1} {2} {3}'.format('#'.ljust(rank), 'PLAYER'.ljust(names), 'TOUCHDOWNS', 'LONGEST HOLD'), yellow))
		for place, player in enumerate(rows, 1):
			await self.sendmsg(chan, '{0} {1} {2} {3}'.format(color(str(place).ljust(rank), grey), player['nick'].ljust(names), color(str(player['touchdowns']).rjust(10), light_blue), human(player['longest'])))
		await self.sendmsg(chan, color('totals: {0:,} passes  {1:,} interceptions'.format(self.passes, self.intercepts), grey))

	async def triggers(self, chan):
		await self.sendmsg(chan, color('WEECHAT', yellow) + color(' (built in trigger plugin)', grey))
		for line in (
			'/trigger add fb_dodge print "*;irc_privmsg,irc_action"',
			'/trigger set fb_dodge conditions "${buffer.short_name} == ' + channel + ' && ${tg_message_nocolor} =~ ^' + nickname + ' .* is charging ${info:irc_nick,${server}}!"',
			'/trigger set fb_dodge command "/msg ' + channel + ' !dodge"',
			'/trigger add fb_intercept print "*;irc_privmsg,irc_action"',
			'/trigger set fb_intercept conditions "${buffer.short_name} == ' + channel + ' && ${tg_message_nocolor} =~ ^' + nickname + ' .* passes the .* to .*\\.$ && ${tg_message_nocolor} !~ ${info:irc_nick,${server}}"',
			'/trigger set fb_intercept command "/msg ' + channel + ' !intercept"',
			'/trigger add fb_grab print "*;irc_privmsg,irc_action"',
			'/trigger set fb_grab conditions "${buffer.short_name} == ' + channel + ' && ${tg_message_nocolor} =~ ^' + nickname + ' .*(fumbled the|hits the ground)"',
			'/trigger set fb_grab command "/msg ' + channel + ' !football"',
			'/set irc.server_default.anti_flood_prio_low 0'):
			await self.sendmsg(chan, line)
		await self.sendmsg(chan, color('IRSSI', yellow) + color(' (needs trigger.pl from scripts.irssi.org, swap ', grey) + color('YOURNICK', cyan) + color(' for your nick)', grey))
		for line in (
			'/script load trigger',
			'/trigger add -pubactions -channels "' + channel + '" -masks "' + nickname + '!*" -regexp "is charging .*YOURNICK" -command "msg ' + channel + ' !dodge"',
			'/trigger add -pubactions -channels "' + channel + '" -masks "' + nickname + '!*" -regexp "passes the .* to (?!.*YOURNICK)" -command "msg ' + channel + ' !intercept"',
			'/trigger add -pubactions -channels "' + channel + '" -masks "' + nickname + '!*" -regexp "(fumbled the|hits the ground)" -command "msg ' + channel + ' !football"',
			'/set cmd_queue_speed 100'):
			await self.sendmsg(chan, line)
		await self.sendmsg(chan, color('the dodge window is only 3 seconds, so keep the flood settings low or your !dodge lands too late', grey))
		await self.sendmsg(chan, color('irssi eats backslashes, so no \\b word boundaries in the regexp, and auto tackling is on you, nothing tracks who has the 🏈', grey))

	async def help(self, chan):
		rows = [
			('@football',        None,     'information about the bot',                                  None),
			('@football help',   None,     'show this help',                                             None),
			('@football scores', None,     'top 10 players by touchdowns',                               None),
			('@football triggers', None,   'weechat & irssi triggers to auto dodge, intercept & pick up', None),
			('!dodge',           None,     'evade a tackle, only in the 3 seconds after one connects',   '(1 in 3)'),
			('!football',        None,     'pick up the 🏈 or see who has it',                           None),
			('!intercept',       None,     'steal the 🏈 within 30 seconds of a pass',                   '(1 in 20)'),
			('!pass',            '<nick>', 'pass the 🏈 to someone',                                     '(1 in 20 is incomplete)'),
			('!tackle',          '<nick>', 'make the holder fumble, or bench anyone else for an hour',   '(once every 5 minutes)')]
		width = max(len(command + (f' {arg}' if arg else '')) for command, arg, _, _ in rows) + 1
		await self.sendmsg(chan, color('COMMAND'.ljust(width) + 'DESCRIPTION', yellow))
		for command, arg, text, note in rows:
			plain = command + (f' {arg}' if arg else '')
			line  = command + (' ' + color(arg, cyan) if arg else '') + ' ' * (width - len(plain)) + color('|', grey) + ' ' + text
			await self.sendmsg(chan, line + (' ' + color(note, grey) if note else ''))
		await self.sendmsg(chan, color('HOW TO PLAY', yellow))
		for step, text in enumerate((
			'{0} picks up a loose 🏈, whoever holds it is the runner'.format(color('!football', light_green)),
			'hold it for 24 hours to score a {0}, every day you keep it scores another one'.format(color('TOUCHDOWN', light_green)),
			'{0} throws it to someone else, {1} passes are incomplete & hit the ground'.format(color('!pass <nick>', light_green), color('1 in 20', white)),
			'for {0} seconds after a pass, anyone but the passer & the receiver can {1} it {2}'.format(color('30', white), color('!intercept', light_green), color('(1 in 20)', grey)),
			'tackling the runner with {0} starts at {1} and gets easier every day they hold it, down to {2}'.format(color('!tackle <nick>', light_green), color('1 in 10', white), color('1 in 3', white)),
			'when a tackle connects the runner has {0} seconds to {1} it {2}, or they go down & fumble'.format(color('3', white), color('!dodge', light_green), color('(1 in 3)', grey)),
			'going down also has a {0} chance of an hour on the bench & a {1} chance of a CTE kick'.format(color('1 in 5', white), color('1 in 100', white)),
			'use {0} on anyone who is not holding the 🏈 to bench them for an hour {1}'.format(color('!tackle <nick>', light_green), color('(1 in 10)', grey)),
			'benched players cannot pick up the 🏈, receive a pass, intercept or tackle',
			'the 🏈 is only lost by a tackle, an incomplete pass, an interception, or by quitting, parting, getting kicked or changing your nick'), 1):
			await self.sendmsg(chan, color(f'{step}.', grey) + ' ' + text)

	async def football(self, nick, args):
		if not self.playable(nick):
			return
		if args == ['!football']:
			if self.ball:
				await self.action(channel, '{0} {1}'.format(color(self.ball, cyan), color('has the 🏈', yellow)))
			else:
				self.ball        = nick
				self.ball_since  = time.time()
				self.ball_scores = 0
				self.ball_pass   = None
				self.player(nick)
				self.save()
				await self.action(channel, '{0} {1}'.format(color(nick, cyan), color('picks up the 🏈', yellow)))
		elif args == ['!dodge'] and self.dodge and self.dodge['holder'].lower() == nick.lower() and time.time() - self.dodge['time'] <= 3:
			tackler    = self.dodge['tackler']
			self.dodge = None
			if self.loops['dodge']:
				self.loops['dodge'].cancel()
			if luck(3):
				await self.action(channel, '{0} {1}'.format(color(nick, cyan), color('spins out of the tackle and stays up! 🏈', yellow)))
			else:
				await self.down(nick, tackler)
		elif args == ['!intercept'] and self.ball_pass and time.time() - self.ball_pass['time'] <= 30 and nick not in (self.ball, self.ball_pass['passer']):
			self.ball_pass = None
			if luck(20):
				victim           = self.ball
				self.intercepts += 1
				self.ball        = nick
				self.ball_since  = time.time()
				self.ball_scores = 0
				self.player(nick)
				self.save()
				await self.action(channel, '{0} {1} {2}{3}'.format(color(nick, cyan), color('INTERCEPTS the 🏈 from', yellow), color(victim, cyan), color('!', yellow)))
			else:
				await self.action(channel, '{0} {1} {2} {3}'.format(color(nick, cyan), color('tries to intercept the 🏈 from', yellow), color(self.ball, cyan), color('and misses!', yellow)))
		elif len(args) != 2:
			return
		elif args[0] == '!pass' and self.ball and nick.lower() == self.ball.lower():
			target = self.members.get(args[1].lower())
			if not target:
				await self.action(channel, '{0} {1} {2} {3}'.format(color(nick, cyan), color('looks around for', yellow), color(args[1], cyan), color('but they are not in the channel...', yellow)))
			elif target.lower() != nick.lower() and self.playable(target):
				if luck(20):
					self.ball        = None
					self.ball_scores = 0
					self.ball_pass   = None
					self.save()
					await self.action(channel, '{0}{1} {2} {3}'.format(color(nick, cyan), color("'s pass to", yellow), color(target, cyan), color('is incomplete! The 🏈 hits the ground.', yellow)))
				else:
					self.passes     += 1
					self.ball        = target
					self.ball_since  = time.time()
					self.ball_scores = 0
					self.ball_pass   = {'passer':nick,'time':time.time()}
					self.player(target)
					self.save()
					await self.action(channel, '{0} {1} {2}{3}'.format(color(nick, cyan), color('passes the 🫳🏈 to', yellow), color(target, cyan), color('.', yellow)))
		elif args[0] == '!tackle' and not self.dodge and (not self.ball or nick.lower() != self.ball.lower()) and time.time() - self.tackles.get(nick.lower(), 0) >= 300:
			target = self.members.get(args[1].lower())
			if not target or target.lower() == nick.lower() or target.lower() in football_blocked or not self.playable(target):
				return
			self.tackles[nick.lower()] = time.time()
			if self.ball and target.lower() == self.ball.lower():
				if luck(self.odds()):
					self.dodge = {'holder':target,'tackler':nick,'time':time.time()}
					self.loops['dodge'] = asyncio.create_task(self.loop_dodge(target, nick))
					await self.action(channel, '{0} {1} {2}{3} {2} {4}'.format(color(nick, cyan), color('is charging', yellow), color(target, cyan), color('!', yellow), color('has 3 seconds to !dodge', yellow)))
				else:
					await self.action(channel, '{0} {1} {2} {3}'.format(color(nick, cyan), color('tries to tackle', yellow), color(target, cyan), color('and misses!', yellow)))
			elif luck(10):
				await self.bench(target)
				await self.action(channel, '{0} {1} {2}{3} {2} {4}'.format(color(nick, cyan), color('levels', yellow), color(target, cyan), color('!', yellow), color('is benched for an hour.', yellow)))
			else:
				await self.action(channel, '{0} {1} {2} {3}'.format(color(nick, cyan), color('tries to tackle', yellow), color(target, cyan), color('and misses!', yellow)))

	async def listen(self):
		while True:
			try:
				if self.reader.at_eof():
					break
				data = await asyncio.wait_for(self.reader.readuntil(b'\r\n'), 600)
				line = data.decode('utf-8').strip()
				args = line.split()
				debug(line)
				if line.startswith('ERROR :Closing Link:'):
					raise Exception('Connection has closed.')
				elif args[0] == 'PING':
					await self.raw('PONG '+args[1][1:])
				elif args[1] == '001':
					if user_modes:
						await self.raw(f'MODE {nickname} +{user_modes}')
					if operator_password:
						await self.raw(f'OPER {operator_name} {operator_password}')
					if os.path.isfile(password_file):
						with open(password_file) as password:
							await self.sendmsg('NickServ', f'IDENTIFY {nickname} {password.read().strip()}')
					else:
						self.loops['register'] = asyncio.create_task(self.loop_register())
					await self.raw(f'JOIN {channel} {key}') if key else await self.raw('JOIN ' + channel)
					self.loops['touchdowns'] = asyncio.create_task(self.loop_touchdowns())
				elif args[1] == '433':
					error('The bot is already running or nick is in use.') # nick change
				elif args[1] == 'NOTICE' and self.pending and args[0].split('!')[0][1:].lower() == 'nickserv':
					if 'registered' in line.lower() and 'already' not in line.lower():
						with open(password_file, 'w') as password:
							password.write(self.pending)
						os.chmod(password_file, 0o600)
						debug('the nick is registered, saved the password to ' + password_file)
						self.pending = None
				elif args[1] == 'INVITE' and len(args) == 4:
					invited = args[2]
					chan    = args[3][1:]
					if invited == nickname and chan == channel:
						await self.raw(f'JOIN {channel} {key}') if key else await self.raw('JOIN ' + channel)
				elif args[1] == 'KICK' and len(args) >= 4:
					chan   = args[2]
					kicked = args[3]
					if chan == channel:
						self.members.pop(kicked.lower(), None)
						await self.fumble(kicked)
					if kicked == nickname and chan == channel:
						self.members = dict()
						await asyncio.sleep(3)
						await self.raw(f'JOIN {channel} {key}') if key else await self.raw('JOIN ' + channel)
				elif args[1] == 'PART' and len(args) >= 3:
					if args[2] == channel:
						nick = args[0].split('!')[0][1:]
						self.members.pop(nick.lower(), None)
						await self.fumble(nick)
				elif args[1] == 'JOIN' and len(args) >= 3:
					if args[2].lstrip(':') == channel:
						nick = args[0].split('!')[0][1:]
						self.members[nick.lower()] = nick
				elif args[1] == 'QUIT':
					nick = args[0].split('!')[0][1:]
					self.members.pop(nick.lower(), None)
					await self.fumble(nick)
				elif args[1] == 'NICK' and len(args) >= 3:
					nick = args[0].split('!')[0][1:]
					if self.members.pop(nick.lower(), None):
						new_nick = args[2].lstrip(':')
						self.members[new_nick.lower()] = new_nick
					await self.fumble(nick)
				elif args[1] == '353' and len(args) >= 6:
					if args[4] == channel:
						for name in ' '.join(args[5:])[1:].split():
							name = name.lstrip('~&@%+')
							self.members[name.lower()] = name
				elif args[1] == 'PRIVMSG' and len(args) >= 4:
					nick = args[0].split('!')[0][1:]
					chan = args[2]
					msg  = ' '.join(args[3:])[1:]
					if chan == channel:
						if msg == '@football':
							await self.sendmsg(chan, bold + 'IRC Football - Developed by acidvegas in Python - https://git.acid.vegas/ircfootball')
						elif msg == '@football help':
							await self.help(chan)
						elif msg == '@football scores':
							await self.scores(chan)
						elif msg == '@football triggers':
							await self.triggers(chan)
						else:
							await self.football(nick, msg.split())
			except (UnicodeDecodeError, UnicodeEncodeError):
				pass
			except Exception as ex:
				error('fatal error occured', ex)
				break

# Main
asyncio.run(Bot().connect())
