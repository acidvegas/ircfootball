# IRC FOOTBALL
> throw the pigskin around your channel

## Information
A football lives in your channel. Anyone can pick it up, throw it to somebody else, steal it out of the air, or flatten the poor bastard holding it.

Hold the football for 24 hours and you score a touchdown. Every day you keep it scores another one, but each day also makes you easier to tackle, so the hoarders get hunted. Touchdowns are tracked per nick forever and shown in `@football scores`.

Lose the football by getting tackled, throwing an incomplete pass, quitting, parting, getting kicked, or changing your nick.

This started as a mode inside [CANCER](https://git.acid.vegas/cancer) and was split out into its own bot.

## Commands
| Command              | Description                                                                 |
| -------------------- | --------------------------------------------------------------------------- |
| `@football`          | Information about the bot                                                   |
| `@football help`     | Show the list of commands                                                   |
| `@football scores`   | Top 10 players by touchdowns *(with their longest hold)*                    |
| `@football triggers` | Client triggers for weechat & irssi to auto dodge, intercept and pick up    |
| `!dodge`             | Evade a tackle in the 3 seconds after it connects *(1 in 3)*                |
| `!football`          | Pick up the football or see who has it                                      |
| `!intercept`         | Steal the football within 30 seconds of a pass *(1 in 20)*                  |
| `!pass <nick>`       | Pass the football to someone *(1 in 20 chance it is incomplete)*            |
| `!tackle <nick>`     | Tackle the holder or bench another player *(once every 5 minutes per nick)* |

## Tackling
When a tackle connects, the holder has 3 seconds to `!dodge` it. A dodge works 1 in 3 times and leaves them on their feet with the football and their touchdown progress intact. Miss the roll or say nothing and they go down: the football is loose for anyone to pick up, with a 1 in 5 chance they are benched for an hour and a 1 in 100 chance they get kicked for CTE.

Tackling anyone who is not holding the football benches them for an hour *(1 in 10)*. While benched you cannot pick up the football, be passed to, intercept, or tackle, and tackling someone who is already benched is ignored.

The odds of tackling the holder start at 1 in 10 and get better for every day they hold it, down to a floor of 1 in 3:

| Days held | 0    | 1   | 2   | 3   | 4   | 5   | 6   | 7+  |
|-----------|------|-----|-----|-----|-----|-----|-----|-----|
| Odds      | 1/10 | 1/9 | 1/8 | 1/7 | 1/6 | 1/5 | 1/4 | 1/3 |

## Setup
Edit the settings at the top of `football.py` and run it:

```shell
python football.py
```

The bot registers its own nick with NickServ two hours after connecting *(networks tend to delay new registrations)*, saves the random password it used to `football_password.txt`, and identifies with it on every connect after that.

Touchdowns, the current holder, and how long they have held it are saved to `football.json` on every change, so a restart does not wipe anyone's progress.

## Todo
- Field position & yard lines so the football can be driven down the field
- Teams with per-team scores
- `!hailmary` for a long pass to a random player

___

###### Mirrors for this repository: [acid.vegas](https://git.acid.vegas/ircfootball) • [SuperNETs](https://git.supernets.org/acidvegas/ircfootball) • [GitHub](https://github.com/acidvegas/ircfootball) • [GitLab](https://gitlab.com/acidvegas/ircfootball) • [Codeberg](https://codeberg.org/acidvegas/ircfootball)

---

###### Mirrors: [SuperNETs](https://git.supernets.org/acidvegas/) • [GitHub](https://github.com/acidvegas/) • [GitLab](https://gitlab.com/acidvegas/) • [Codeberg](https://codeberg.org/acidvegas/)
