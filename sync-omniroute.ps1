# 1. Удаляем базу SQLite и бэкапы из индекса Git (они останутся на диске, но Git перестанет их видеть)
git rm -r --cached "omniroute - backup" 2>$null
git rm -r --cached "omniroute-backup" 2>$null
git rm -r --cached ".tmp.driveupload" 2>$null
git rm -r --cached "storage.sqlite" "storage.sqlite-shm" "storage.sqlite-wal" 2>$null

# 2. Записываем в .gitignore, чтобы Git больше НИКОГДА не трогал эти файлы
 $gitignore = "
# OmniRoute Databases & Backups
storage.sqlite
storage.sqlite-shm
storage.sqlite-wal
omniroute-backup/
omniroute - backup/
server.env
call_logs/
db_backups/
logs/

# Temp files
.tmp.driveupload/
"
Add-Content -Path .gitignore -Value $gitignore

# 3. Коммитим это очищение
git add -A
git commit -m "fix: massive cleanup of tmp files and omniroute databases from git"

# 4. Пушим в главную ветку
git push origin main