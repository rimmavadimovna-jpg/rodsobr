# Запуск бота на бесплатном сервере 24/7 (Oracle Cloud Always Free)

Цель: бот работает круглосуточно для всех пользователей, даже когда ваш
компьютер выключен. Прогресс учеников сохраняется (файл `bank.sqlite` лежит
на диске сервера).

Это разовая настройка. Дальше бот просто работает; обновления — `git pull`.

---

## Часть 0. Подготовка (на вашем компьютере)

1. Залейте текущий код в GitHub через **GitHub Desktop**:
   - откройте GitHub Desktop → слева увидите изменённые файлы → внизу впишите
     summary (напр. `server deploy files`) → **Commit to main** → вверху **Push origin**.
2. Сделайте репозиторий **публичным** (так проще клонировать на сервер):
   - на GitHub откройте репозиторий `rodsobr` → **Settings** → внизу
     **Danger Zone** → **Change visibility** → **Make public**.
   - (Если хотите оставить приватным — на сервере при `git clone` нужно будет
     ввести логин и токен GitHub; публичный проще.)

---

## Часть 1. Создать бесплатную виртуальную машину

1. Зарегистрируйтесь на https://www.oracle.com/cloud/free/ (нужна карта для
   верификации личности — деньги НЕ списываются на Always Free).
2. В консоли: **Menu → Compute → Instances → Create Instance**.
3. Параметры:
   - **Image**: Canonical **Ubuntu 24.04**.
   - **Shape**: любой с пометкой **Always Free-eligible**
     (`VM.Standard.E2.1.Micro` или Ampere `VM.Standard.A1.Flex` 1 OCPU / 6 ГБ).
   - **SSH keys**: выберите **Generate a key pair for me** и **скачайте**
     приватный ключ (`.key`) — он понадобится для входа.
4. **Create**. Запомните **Public IP address** созданной машины.

---

## Часть 2. Подключиться к серверу

Проще всего — через браузерный **Cloud Shell** (кнопка справа вверху в консоли
Oracle, иконка `>_`): терминал открывается прямо в браузере, ключ уже подставлен.

Либо по SSH с компьютера (PowerShell), подставив путь к скачанному ключу и IP:
```
ssh -i C:\путь\к\ключу.key ubuntu@ВАШ_IP
```

---

## Часть 3. Установить и запустить бота (команды на сервере)

Скопируйте блоки по очереди. Замените `ВАШ_ЛОГИН` на ваш GitHub-логин
(`rimmavadimovna-jpg`) в адресе репозитория.

```bash
# системные пакеты
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

# клонировать проект
cd ~
git clone https://github.com/ВАШ_ЛОГИН/rodsobr.git
cd rodsobr

# виртуальное окружение и зависимости
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# собрать банк заданий
.venv/bin/python -m letovo_bot.data.build_bank
```

Должно появиться `тестовых вопросов (QUIZ): 135`.

### Прописать токен бота

```bash
# создаём файл с токеном (вставьте свой токен от BotFather вместо ТОКЕН)
echo 'TELEGRAM_BOT_TOKEN=ТОКЕН' | sudo tee /etc/letovo-bot.env
sudo chmod 600 /etc/letovo-bot.env
```

### Настроить автозапуск (служба systemd)

```bash
# скопировать готовый файл службы и включить автозапуск
sudo cp ~/rodsobr/deploy/letovo-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now letovo-bot
```

Проверить, что бот работает:
```bash
systemctl status letovo-bot --no-pager
journalctl -u letovo-bot -n 20 --no-pager
```
Ищите строку `Бот запущен`. Готово — бот работает 24/7 и сам перезапустится
после перезагрузки сервера.

---

## Часовой пояс рассылки

Время рассылки задаётся в боте (хранится по каждому пользователю). После старта
отправьте боту в Telegram:
```
/settings tz Europe/Moscow
/settings time 10:00
```

---

## Обновления в будущем

Когда поменяете задания/код и зальёте в GitHub (через Desktop), на сервере:
```bash
cd ~/rodsobr
git pull
.venv/bin/pip install -r requirements.txt        # если менялись зависимости
.venv/bin/python -m letovo_bot.data.build_bank    # пересобрать банк
sudo systemctl restart letovo-bot
```

## Полезные команды

```bash
sudo systemctl restart letovo-bot   # перезапустить
sudo systemctl stop letovo-bot      # остановить
journalctl -u letovo-bot -f         # смотреть логи в реальном времени (выход — Ctrl+C)
```
