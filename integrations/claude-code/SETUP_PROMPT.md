# Claude Code — Setup Prompt for minder-memory

Скорми этот документ своему Claude Code вместе с путём до клона
`minder-memory`. CC выполнит установку одной командой и отчитается.

Установка полностью автоматизирована: `install.sh` рендерит шаблоны,
делает симлинки в `~/.claude/{rules,commands,skills}/` и сам подключает
нужные `@`-импорты в `~/.claude/CLAUDE.md` через managed block (с
бэкапом). Идемпотентно — повторный запуск после `git pull` обновляет
блок на месте.

---

## Вход

`<MINDER_MEMORY_PATH>` — абсолютный путь до клона репозитория `minder-memory`
(содержит `zettelkasten/`, `integrations/claude-code/`, `scripts/`).

Если не передан — спроси и остановись.

---

## Что сделать

1. **Проверить клон.** Убедиться, что `<MINDER_MEMORY_PATH>` существует и
   это git-репозиторий с `integrations/claude-code/install.sh` и
   `zettelkasten/_system/`. Если нет — остановиться, сообщить.

2. **Запустить установщик:**
   ```bash
   bash <MINDER_MEMORY_PATH>/integrations/claude-code/install.sh
   ```
   Показать вывод пользователю. Если упал — отдать stderr, не чинить
   вслепую.

3. **Smoke test** — кратко выполнить и сообщить:
   - `ls -la ~/.claude/rules/minder-memory.md ~/.claude/skills/minder-mem-process` — проверить, что симлинки живые.
   - `git -C <MINDER_MEMORY_PATH> pull --rebase --autostash` — убедиться, что pull работает (если remote настроен).
   - Проверить, что в `~/.claude/CLAUDE.md` появился managed block с `<!-- MINDER-MEMORY BEGIN ... -->`.

4. **Финальный отчёт:**
   - Что установилось, где бэкап (если был).
   - Подсказать пользователю **перезапустить Claude Code / открыть новую сессию**, чтобы правила подхватились.
   - Если SOUL.md или другие derived views ещё не сгенерены — упомянуть, что после первого batch стоит прогнать `/minder:mem:regen-constitution`.
   - **Если пользователь планирует автоматический шедулер** (Claude Code
     `/schedule`, cron, GitHub Actions): напомнить включить в GitHub repo
     **Settings → General → Pull Requests → ☑ Automatically delete head
     branches**. Без этой галки в Cloud Routines режиме каждый tick
     оставляет sandbox-ветку на origin — proxy блокирует
     `git push origin --delete`, MCP сервер не имеет `delete_branch`,
     удаление делегировано самому GitHub. Подробности — `docs/scheduling.md`
     раздел «Required repo setting».

---

## Что устанавливается (для информации, не делать руками)

`install.sh` создаёт в `~/.claude/`:

**Rules** (auto-loaded через managed block в `~/.claude/CLAUDE.md`):
- `minder-memory.md` — search triggers (reactive + narrow proactive) + `/minder:mem:check-decision` discovery
- `constitution-capture.md` — глобальный capture-hook (4 узких триггера)
- `constitution-core.md` — derived view конституции (аксиомы / принципы / правила)

**Rules** (симлинки, on-demand, не auto-loaded):
- `minder-memory-engine-doctrine.md` — operating philosophy движка; читается скиллами

**Commands:** `minder:mem:search`, `minder:mem:recap`

**Skills:** `minder:mem:agent-lens-add`, `minder:mem:agent-lens`, `minder:mem:bootstrap`,
`minder:mem:capture-candidate`, `minder:mem:content`, `minder:mem:check-decision`,
`minder:mem:lint`, `minder:mem:maintain`, `minder:mem:process`, `minder:mem:regen-constitution`,
`minder:mem:resolve-clarifications`, `minder:mem:role:add`, `minder:mem:role:ask`,
`minder:mem:role:edit`, `minder:mem:role:list`, `minder:mem:roles`, `minder:mem:save`,
`minder:mem:source-add`, `minder:mem:sync-data`, `minder:mem:update`

---

## Откат

```bash
bash <MINDER_MEMORY_PATH>/integrations/claude-code/uninstall.sh
```

Снимает только то, что поставил `install.sh`: симлинки, указывающие в
этот репозиторий, и managed block в `~/.claude/CLAUDE.md`. Бэкапы под
`~/.claude/.minder-memory-backup-*` сохраняются.

---

## Если что-то идёт не так

- Установка упала → показать stderr, проверить права на `~/.claude/`
  и `<MINDER_MEMORY_PATH>`. Не запускать повторно вслепую.
- Симлинки не подхватились → перезапустить CC.
- Скилл `/minder:mem:*` не находится → проверить `ls ~/.claude/skills/`. Если
  пусто — `install.sh` упал молча, перезапустить через `bash -x`.
- `git pull` ругается на divergent branches → не чинить, отдать
  пользователю.

Никаких деструктивных действий без подтверждения: `rm -rf`, `git reset
--hard`, `--force` push, удаление бэкапов.
