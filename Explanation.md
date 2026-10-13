# CKE: sistem necə işləyir (Explanation.md)

Bu sənəd Cyber Knowledge Engine-in **təmirdən sonrakı** halını təsvir edir (HEAD, 2026-10-13). Məqsəd budur: kodu yenidən oxumadan onun haqqında istənilən suala cavab verə biləsiniz.

Qaydalar:

- `file:line` istinadları hazırkı koda aiddir.
- Nəyinsə necə işlədiyinə əmin olmadığım yerdə bunu açıq yazmışam, təxmin etməmişəm.
- İngilis terminləri ilk dəfə işlənəndə yanında mötərizədə qısa izah var. Tam lüğət J bölməsindədir.

Bölmələr: A (ümumi baxış) · B (rejimlərin addım-addım izi) · C (modullar) · D (məlumat formaları) · E (prompt-lar) · F (dizayn qərarları) · G (xəta halları) · H (genişləndirmə) · I (məhdudiyyətlər və gələcək iş) · J (lüğət).

---

## A. Ümumi baxış

### Sistem nədir

CKE kibertəhlükəsizlik üzrə xam tədris materialını Obsidian-da atomik qeydlərə çevirən Python pipeline-dır (ardıcıl emal zənciri). Material Hack The Box modulları, lab həlləri və texniki qeydlər ola bilər. İstifadəçi mətni terminalda `kb` əmrinə verir. Sistem bundan sonra:

1. mətni LLM-ə (böyük dil modelinə) göndərir və strukturlu JSON alır;
2. JSON-u Pydantic schema-sı (məlumat formasının qaydası) ilə yoxlayır, səhv olarsa, səhv mesajı ilə yenidən soruşur;
3. qeydi Markdown faylı kimi uyğun kateqoriya qovluğuna yazır;
4. qeydin embedding-ini (mənasını əks etdirən rəqəm vektoru) index faylına əlavə edir ki, sonra oxşar qeydlər tapılsın.

### Tətbiq etdiyi qayda: bir mövzu = bir qeyd

Bu qayda kodda iki yolla tətbiq olunur:

- **İnsan qərarı ilə.** `--split` planı istifadəçiyə göstərilir və istifadəçi qeydləri birləşdirə və ya ata bilər. `--merge`-də isə hədəf qeydi istifadəçi seçir.
- **Fayl səviyyəsində.** Bir slug (başlıqdan düzəldilən fayl adı) həmişə yalnız bir faylda olur (`engine/vault.py:59-70`, `30-42`). Yeni qeyd mövcud faylı heç vaxt əvəz etmir, bunu yalnız merge edə bilər (P0-3). Index də slug ilə açarlanır.

Kodda **avtomatik məna yoxlaması yoxdur.** Adi `kb` yeni qeyd yaradarkən oxşar qeydin olub-olmadığını yoxlamır. "Nmap" və "Nmap Scanning" fərqli slug-lar verdiyi üçün iki ayrı qeyd yarana bilər. Oxşarlıq axtarışı yalnız `kb --merge`-də işləyir.

### İki maşın

README-dəki arxitekturaya görə:

- **Client (M1):** mətni şəbəkə üzərindən server-ə göndərmək üçündür. Bu yol hazırda real istifadədə deyil.
- **Server maşını (M4):** engine, vault, `kb` əmri, Ollama və `engine/server.py` buradadır. Server `~/Library/LaunchAgents/com.cke.server.plist` ilə avtomatik işə düşür. Defolt olaraq yalnız `127.0.0.1:8000`-də dinləyir (`engine/config.py:37-38`).

### Məlumat harada saxlanır

| Nə | Harada | Qeyd |
|---|---|---|
| Qeydlər | `~/Documents/CyberKB/<NN Kateqoriya>/<slug>.md` | `CKE_VAULT` ilə dəyişmək olar (`engine/config.py:5`) |
| Index | `~/Documents/CyberKB/.kb_index.json` | Hər qeyd üçün 768 ölçülü vektor, başlıq və kateqoriya (`engine/config.py:6`) |
| Sirlər | `~/cke/.env` | `DEEPSEEK_API_KEY`; istəyə bağlı `CKE_SERVER_TOKEN`. Git-ə düşmür |
| Server log-u | `~/cke/server.log` | Ona launchd yazır. Git-ə düşmür |
| Tənzimləmələr | `engine/config.py` | Bütün yollar, modellər, hədlər, timeout-lar (iki istisna C bölməsindədir) |

Vault üç yolla sinxronlaşdırılır:

- Syncthing;
- `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/CyberKB/` qovluğuna birtərəfli `rsync --delete` (iPhone üçün). Bunu `~/.zshrc`-dəki `kbphone` alias-ı edir və `.git/`, `.obsidian/`, `.kb_index.json` köçürülmür.

Engine sinxronizasiya ilə məşğul olmur. Amma bunun bir nəticəsi var: `.kb_index.json` Syncthing ilə sinxronlaşan qovluqdadır. Pipeline iki maşında eyni vaxtda işləsə, index-də konflikt yarana bilər.

### Modellər

| Model | Harada | Nə üçün |
|---|---|---|
| `deepseek-flash` | DeepSeek API (`https://api.deepseek.com`) | Defolt chat modeli (`DEFAULT_BACKEND = "api"`) |
| `qwen3:14b` | Lokal Ollama | `--local` ilə chat modeli |
| `nomic-embed-text` | Lokal Ollama | Embedding. `--delete`-dən başqa **hər rejimdə** lazımdır |

---

## B. Rejimlərin addım-addım izi

Hər iz eyni qaydada yazılıb:

- hansı faylda hansı funksiyanın, hansı sıra ilə işlədiyi;
- məlumatın hər addımda hansı formada olduğu;
- LLM-in harada çağırıldığı (**[LLM]**);
- Ollama embedding-inin harada alındığı (**[EMB]**);
- vault-a harada toxunulduğu (**[VAULT]**);
- prosesin harada sına biləcəyi (**[XƏTA]**).

### B.0. Bütün rejimlər üçün ümumi başlanğıc

1. **Shell.** `kb` alias-ı `~/cke/kb`-yə yönəlir (`~/.zshrc:124`). Bu 4 sətirlik skript `cd ~/cke` edir, `venv`-i aktivləşdirir və `python3 -m engine.cli "$@"` işə salır.
2. **Import zənciri.** `engine/cli.py:6-7` `engine.main`-i import edir. `engine/main.py:1` `config`, `memory`, `vault`, `brain`-i import edir. Bu zəncirdə üç vacib iş baş verir:
   - `engine/config.py:5` işləyir: `VAULT` ya `CKE_VAULT` mühit dəyişənindən, ya da defolt yoldan götürülür.
   - `engine/memory.py:2` `llm`-i import edir. `engine/llm.py:10` `.env` faylını yükləyir.
   - Bu sıranın nəticəsi: `config` `.env`-dən **əvvəl** hesablanır, ona görə `CKE_VAULT` `.env`-dən oxunmur.
3. **`cli.run()`** (`engine/cli.py:268`): `args = sys.argv[1:]`.
4. `--delete` varsa, dərhal `handle_delete()` çağırılır (`engine/cli.py:271-273`). Ollama yoxlanmır. İz B.5-dədir.
5. **Ollama yoxlaması** (`engine/cli.py:277`, `require_ollama`):
   - `check_ollama()` (`engine/cli.py:16-25`) `GET http://localhost:11434/api/tags` göndərir (timeout 5 saniyə).
   - HTTP 200 tələb edir.
   - Model adlarını `with_tag()` ilə normallaşdırır: tag-sız ada `:latest` əlavə olunur.
   - `config.EMBED_MODEL`-in siyahıda olub-olmadığını yoxlayır.
   - **[XƏTA]** Ollama sönülüdürsə və ya model yoxdursa: `ERROR: Ollama is not reachable ...` çap olunur və `sys.exit(1)`. Bu, heç bir LLM çağırışından və heç bir yazmadan əvvəl baş verir.
6. `--reindex` varsa, `handle_reindex()` çağırılır (`engine/cli.py:279-281`). İz B.7-dədir.
7. **Backend seçimi** (`engine/cli.py:283-286`): `backend = config.DEFAULT_BACKEND` (`"api"`). `--local` varsa, `backend = "local"` olur və flag siyahıdan silinir.

### B.1. `kb` (yeni qeyd yaratmaq)

1. `--split` və `--writeup` yoxdur. `do_merge = False` (`engine/cli.py:317`).
2. **Giriş mətni** (`engine/cli.py:322`, `get_input_text`, `engine/cli.py:55-70`):
   - `args[0] == "--file"` olarsa, fayl oxunur;
   - başqa arqumentlər varsa, onlar boşluqla birləşdirilir;
   - heç nə yoxdursa, "Paste your note text below" çap olunur və `sys.stdin.read()` Ctrl+D-yə qədər oxuyur.
   - **Forma:** xam `str`, sonra `.strip()`.
   - **[XƏTA]** Mətn 30 simvoldan qısadırsa: `Input too short` çap olunur və `sys.exit(1)` (`engine/cli.py:323-325`).
3. Spinner başlayır, sonra `process(text, backend)` çağırılır (`engine/cli.py:375-378`).
4. **`main.process`** (`engine/main.py:12-26`):
   1. `brain.create_note(text)` (`engine/main.py:14`) → `generate_validated(CREATE_SYSTEM, text)` (`engine/brain.py:127-128`, `112-124`):
      - **[LLM]** `llm.ask_json` (`engine/brain.py:119`) → `_ask_json_api` (`engine/llm.py:56-70`). DeepSeek-ə system və user mesajı gedir: `temperature=0.2`, `top_p=0.95`, `max_tokens=32768`.
      - **Forma:** cavab xam mətndir. `_extract_json` (`engine/llm.py:73-78`) birinci `{` ilə sonuncu `}` arasını kəsib `json.loads` edir və nəticə `dict` olur. Sonra `Note.model_validate(raw)` (`engine/brain.py:120`) onu `Note` obyektinə çevirir.
      - **[XƏTA]** `ValidationError`, `ValueError` və ya `JSONDecodeError` olarsa: səhv mesajı prompt-a əlavə olunur və yenidən soruşulur. Ümumilikdə `MAX_RETRIES + 1 = 3` cəhd edilir. Üçü də uğursuz olsa, `RuntimeError` qaldırılır (`engine/brain.py:124`).
      - **[XƏTA]** `DEEPSEEK_API_KEY` yoxdursa, `RuntimeError` qaldırılır (`engine/llm.py:20`). Şəbəkə və ya auth xətaları (`openai`-nin exception-ları) da retry olunmur, çünki `generate_validated` yalnız yuxarıdakı üç növü tutur. Hər iki halda `cli` `ERROR: ...` çap edir və `exit(1)` edir.
   2. `slug = vault.slugify(note.title)` (`engine/main.py:15`, `engine/vault.py:79-94`). Nəticə həmişə boş olmayan `str`-dir. Sonra `vault.ensure_new(slug)` (`engine/main.py:17`, `engine/vault.py:52-56`) bu slug-ın hər hansı kateqoriyada olub-olmadığını yoxlayır.
      - **[XƏTA]** Slug artıq varsa, `NoteExistsError` qalxır, kateqoriya çağırışı edilmir və **heç nə yazılmır**. `cli` `STOPPED: a note with this filename already exists. Nothing was written.` çap edir. Sonra mövcud qeydin başlığını (fayldan oxunur), kateqoriyasını və yolunu göstərir, `kb --merge` təklif edir və `exit(1)` edir (`engine/cli.py:382-385`, `report_existing`: `44-52`).
   3. `brain.choose_category(title, summary)` (`engine/main.py:20`, `engine/brain.py:156-165`):
      - **[LLM]** `CATEGORY_SYSTEM` ilə ikinci çağırış.
      - Cavab `config.CLASSIFIER_CATEGORIES`-də deyilsə, və ya hər hansı xəta olsa, `"00 Inbox"` qaytarılır. Bu funksiya **heç vaxt** exception qaldırmır.
   4. `save_note(slug, category, note)` (`engine/main.py:23`, `4-9`). Üç addım bu sıra ilə gedir:
      1. **[EMB]** `memory.embed_entry` (`engine/memory.py:24-30`) → `llm.embed` (`engine/llm.py:25-33`): `POST /api/embeddings`, mətn `"{title}\n{summary}"`-dir, ilk 6000 simvola qədər kəsilir, timeout 60 saniyədir. **Forma:** `{"vector": [768 float], "title": ..., "category": ...}`. **[XƏTA]** Ollama düşübsə, `requests` exception-u qalxır və **heç nə yazılmır**.
      2. **[VAULT]** `vault.write_note` (`engine/vault.py:59-70`):
         - `find_note(slug)` köhnə yeri tapır. Slug iki kateqoriyada varsa, `RuntimeError` qaldırır.
         - Slug artıq varsa və `replace=False`-dursa, `NoteExistsError` qalxır. Merge-dən başqa bütün yollarda `replace=False`-dur. `process` bunu 2-ci addımda yoxlayıb, bu isə son qorumadır.
         - Lazım olsa, qovluq yaradılır.
         - `<VAULT>/<category>/<slug>.md` faylına `to_markdown(note)` yazılır (`engine/vault.py:97-104`).
         - `replace=True` ilə (yalnız merge) slug başqa kateqoriyada idisə, köhnə fayl silinir.
      3. **[VAULT]** `memory.save_entry` (`engine/memory.py:33-36`): bütün index oxunur, `index[slug] = entry` yazılır, bütün index yenidən yazılır.
5. `create: <category>/<slug>.md` çap olunur. `cli` sonra `Done. Note saved as: <slug>.md` çap edir.

**Xülasə:** 2 LLM çağırışı (retry ilə ən çox 4), 1 embedding, 2 disk yazısı. Slug artıq varsa, 1 LLM çağırışından sonra dayanır və heç nə yazmır.

### B.2. `kb --split` (modulu atomik qeydlərə bölmək)

1. `--split` siyahıdan silinir. `split_text = get_input_text(args)` oxunur, sonra `handle_split(backend, split_text)` çağırılır (`engine/cli.py:288-292`).
2. **`handle_split`** (`engine/cli.py:100-199`): mətn `.strip()` edilir. **[XƏTA]** 100 simvoldan qısadırsa: `Input too short ... for splitting` çap olunur və funksiya qayıdır. Burada `exit(1)` olmur.
3. **Plan** (`engine/cli.py:115`): `propose_split_plan` (`engine/main.py:137-138`) → `brain.propose_split` (`engine/brain.py:203-206`):
   - **[LLM]** `generate_validated(SPLIT_SYSTEM, text, schema=SplitPlan)`. Retry yolu notlarla eynidir.
   - **Forma:** `dict` → `SplitPlan` obyekti → `[entry.model_dump() ...]`, yəni `{"title", "type", "covers", "source_hint"}` dict-lərindən ibarət siyahı.
   - **[XƏTA]** Plan son cəhddən sonra da yararsızdırsa: `ERROR during planning: ...` çap olunur və funksiya qayıdır. Heç nə yazılmır.
4. Plan boşdursa, `No notes proposed. Nothing saved.` çap olunur (`engine/cli.py:122-124`).
5. **İnsanın təsdiqi** (`engine/cli.py:126-172`). Plan nömrələnmiş şəkildə göstərilir. Hər dəfə plan göstəriləndə `main.notes_on_disk()` (`engine/main.py:82-90`) vault-u bir dəfə skan edir. Elementin başlığından alınan slug artıq diskdədirsə, sətrin sonuna `[exists: <kateqoriya>]` əlavə olunur, siyahının altında isə belə elementin keçiləcəyi izah edilir (`engine/cli.py:127-137`). Onu `drop` ilə atmaq olar. Seçimlər:
   - Enter: hamısını yarat;
   - `cancel`: dayandır;
   - `merge 2 3`: seçilənlər birləşir. Başlıq birinci seçilənin başlığı olur, `type` həmişə `"technique"` olur, `covers` və `source_hint` birləşdirilir. Yeni element siyahının əvvəlinə qoyulur;
   - `drop 4`: elementi at.
6. **Hər plan elementi üçün** (`engine/cli.py:178-193`): `process_from_plan(text, entry, backend)` çağırılır (`engine/main.py:140-164`):
   1. `slug = slugify(note_plan["title"])` və `ensure_new(slug)` (`engine/main.py:148-149`). Bu yoxlama **heç bir model çağırışından əvvəl** olur. **[XƏTA]** Slug artıq varsa, `NoteExistsError` qalxır. `handle_split` onu tutur, `skipped (already exists): <kateqoriya>/<slug>.md` çap edir və növbəti elementə keçir (`engine/cli.py:186-190`). Mövcud qeydə toxunulmur və model çağırılmır. Eyni plandakı iki başlıq eyni slug verirsə (`Whois` və `whois`), birincisi yazılır, ikincisi keçilir.
   2. `focus_prompt` qurulur (`engine/main.py:150-158`). Bu, **bütün** mənbə mətni və əlavə göstərişlərdir: "yalnız bu başlığa fokuslan", `covers`, `source_hint`.
   3. **[LLM]** `brain.create_note(focus_prompt)`.
   4. `note.title = note_plan["title"]` (`engine/main.py:161`). Başlıq olaraq modelin yaratdığı yox, istifadəçinin təsdiqlədiyi qısa başlıq götürülür. Pydantic təyin etməni (assignment) yenidən yoxlamır, amma bu başlıq artıq `PlanEntry`-də yoxlanıb.
   5. **[LLM]** `choose_category`, sonra **[EMB]** + **[VAULT]** `save_note`. Slug 1-ci addımda hesablanıb.
   6. **[XƏTA]** Bir qeyddə başqa xəta olarsa, `ERROR on '<title>'` çap olunur və **növbəti qeydə keçilir**. Artıq yaradılmış qeydlər qalır.
7. Sonda `Done. Created N note(s).` çap olunur. Keçilən element varsa, `Skipped M existing note(s), not overwritten:` və hər birinin yolu çap olunur (`engine/cli.py:194-199`).

**Xülasə:** N qeyd üçün `1 + 2N` LLM çağırışı (retry-lər bura daxil deyil). Keçilən qeyd model çağırmır. Mənbə mətnin hamısı hər qeyd üçün yenidən göndərilir, ona görə xərc təxminən `N × mətnin uzunluğu` qədərdir (I bölməsi, gələcək iş 3).

### B.3. `kb --writeup` (maşın həllini writeup-a çevirmək)

1. `--writeup` siyahıdan silinir, mətn oxunur və `.strip()` edilir (`engine/cli.py:294-297`). **[XƏTA]** 100 simvoldan qısadırsa, funksiya qayıdır (`engine/cli.py:298-300`).
2. Spinner başlayır, sonra `process_writeup(text, backend)` çağırılır (`engine/main.py:166-173`):
   1. **[LLM]** `brain.create_writeup` (`engine/brain.py:247-248`) → `generate_validated(WRITEUP_SYSTEM, text)` → `Note`.
   2. `category = "90 Writeups"`. Bu, sabit dəyərdir, classifier çağırılmır.
   3. `slugify`, sonra **[EMB]** + **[VAULT]** `save_note`. Bu adda writeup artıq varsa, `write_note` `NoteExistsError` qaldırır və heç nə yazılmır (P0-3). Başlıq yalnız modelin cavabından sonra bəlli olur, ona görə API çağırışı artıq edilmiş olur. `--merge` təklif olunmur, çünki merge writeup-u ensiklopediya prompt-u ilə yenidən yazardı.
3. **[XƏTA]** İstənilən exception-da `ERROR: ...` çap olunur və `exit(1)` (`engine/cli.py:311-314`).

**Xülasə:** 1 LLM çağırışı (retry ilə ən çox 3), 1 embedding, 2 disk yazısı.

### B.4. `kb --merge` (yeni məlumatı mövcud qeydə birləşdirmək)

1. `do_merge = True` olur, flag siyahıdan silinir (`engine/cli.py:317-320`). Mətn B.1-dəki kimi oxunur. **[XƏTA]** 30 simvoldan qısadırsa, `exit(1)`.
2. **Oxşar qeydlərin axtarışı** (`engine/cli.py:331-335`): `find_merge_candidates(text)` (`engine/main.py:29-30`) → `memory.find_top_matches(text, limit=5)` (`engine/memory.py:45-56`):
   1. `load_index()`. Index boşdursa, `[]` qaytarılır.
   2. **[EMB]** `llm.embed(text)`: yeni mətnin vektoru (ilk 6000 simvol).
   3. Index-dəki **hər** yazı ilə cosine similarity (iki vektorun istiqamət oxşarlığı) hesablanır (`engine/memory.py:15-21`).
   4. Nəticələr azalan sıra ilə düzülür, `>= CANDIDATE_THRESHOLD` (0.60) olanlar saxlanır, ən çox 5-i götürülür.
   - **Forma:** `[(slug, title, category, score), ...]`.
3. Namizəd yoxdursa: `No sufficiently similar notes found. Creating a new note instead.` çap olunur, `do_merge = False` olur və axın **B.1-ə** keçir (adi qeyd yaradılır).
4. Namizədlər göstərilir və `input()` ilə seçim alınır (`engine/cli.py:341-345`):
   - `0` və ya rəqəm olmayan cavab: yeni qeyd yaradılır (B.1);
   - aralıqdan kənar rəqəm: `Invalid choice` və `exit(1)`;
   - düzgün seçim: `target_slug` götürülür.
5. Spinner başlayır və `ask_rename` funksiyası qurulur (`engine/cli.py:357-359`). Bu funksiya əvvəl spinner-i dayandırır, sonra `confirm_rename`-i çağırır.
6. **`merge_into(text, target_slug, backend, confirm_rename=ask_rename)`** (`engine/main.py:33-71`):
   1. `vault.read_note(target_slug)` (`engine/vault.py:45-49`). **[XƏTA]** Fayl yoxdursa, `RuntimeError: Note '...' not found`. Bu, index-də ghost yazı olanda baş verir və `kb --reindex` bunu təmizləyir. Slug dublikatdırsa, `find_note` `RuntimeError` qaldırır.
   2. `vault.markdown_to_json(existing_md)` (`engine/vault.py:107-139`). **Forma:** `{"title", "summary", "sections": [{"heading", "content"}]}`. Fence-lərin içi məzmundur, başlığı yalnız birinci `# ` sətri təyin edir.
   3. `find_note` yenidən çağırılır və mövcud kateqoriya götürülür.
   4. **[LLM]** `brain.create_note(text)`: yeni mətn strukturlaşdırılır.
   5. **[LLM]** `brain.merge_two_notes(existing_json, new_note.model_dump())` (`engine/brain.py:131-133`). Prompt hər iki qeydin JSON-udur, nəticə `Note`-dur.
   6. `new_slug = slugify(merged.title, fallback=False)` (`engine/main.py:46`). **[XƏTA]** Slug boşdursa: `RuntimeError(... Nothing was changed.)`. Vault-a toxunulmayıb.
   7. Slug dəyişibsə, əvvəl yeni slug-ın başqa qeydə aid olub-olmadığı yoxlanır (`engine/main.py:52-57`). Aiddirsə, sual verilmir, fayl adı köhnə qalır və `Title changed to '...', but <kateqoriya>/<slug>.md is another note; keeping the filename ...` çap olunur. Aid deyilsə, `confirm_rename(target, new)` çağırılır (`engine/cli.py:35-41`):
      - `stdin` TTY deyilsə, cavab `False` olur;
      - əks halda köhnə və yeni ad göstərilir və `yes/no` soruşulur.
      - `yes` deyilsə, fayl adı köhnə qalır və `Title changed to ...; keeping the filename ...` çap olunur.
   8. `category = existing_category or "00 Inbox"`. Merge-də classifier **çağırılmır**, qeyd öz qovluğunda qalır.
   9. **[EMB]** + **[VAULT]** `save_note(new_slug, category, merged, replace=new_slug == target_slug)` (`engine/main.py:65`): əvvəl embedding, sonra fayl, sonra index. `replace=True` yalnız birləşdirilən qeydin öz slug-ı üçündür, yəni merge başqa qeydi əvəz edə bilməz.
   10. Rename təsdiqlənibsə, **[VAULT]** `vault.delete_note(target_slug)` və `memory.remove_entry(target_slug)` çağırılır. Bu silmə yalnız yeni fayl və onun index yazısı uğurla yazıldıqdan sonra baş verir.
7. `Done. Merged into: <slug>.md` çap olunur. **[XƏTA]** İstənilən exception-da `ERROR: ...` və `exit(1)`.

**Xülasə:** 2 LLM çağırışı, 2 embedding (biri axtarış, biri saxlama üçün), 2 və ya 4 disk əməliyyatı.

### B.5. `kb --delete` (qeydi silmək)

1. `--delete` **ilk** yoxlanılan flag-dır (`engine/cli.py:271-273`). Ona görə Ollama yoxlanmır və başqa flag-lar nəzərə alınmır.
2. **`handle_delete`** (`engine/cli.py:201-233`):
   1. `list_all_notes()` (`engine/main.py:73-79`). Yalnız `config.VAULT_CATEGORIES`-də olan mövcud qovluqlar gəzilir (`vault.category_dirs()`), qovluqlar `config` sırası ilə, fayllar isə əlifba sırası ilə. **Forma:** `[(slug, category), ...]`. `Claude outputs/` kimi qovluqlar görünmür.
   2. Nömrələnmiş siyahı göstərilir və `input()` ilə seçim alınır. `0` və ya yararsız cavab: `Cancelled`.
   3. `Delete '<slug>'? ... (yes/no)` soruşulur. Yalnız `yes` cavabı silir.
   4. `delete_note_by_slug(slug)` (`engine/main.py:129-135`) üç iş görür:
      - `find_note`. **[XƏTA]** Dublikat varsa `RuntimeError` qalxır, `cli` bunu `ERROR: ...` kimi çap edir və **heç nə silinmir**;
      - **[VAULT]** `vault.delete_note`: fayl silinir;
      - **[VAULT]** `memory.remove_entry`: index-dən silinir.
3. LLM çağırışı və embedding yoxdur.

### B.6. `kb --local` (lokal model ilə)

`--local` ayrıca rejim deyil, **modifikator**dur. O, `backend = "local"` təyin edir (`engine/cli.py:284-286`) və yuxarıdakı istənilən rejimlə birlikdə işləyir: `kb --local`, `kb --split --local` və s. Fərq yalnız `llm.ask_json`-dadır (`engine/llm.py:81-86`):

1. `_ask_json_local` (`engine/llm.py:36-53`): `POST http://localhost:11434/api/generate`. Göndərilənlər:
   - `model = qwen3:14b`, `system`, `prompt`, `stream: false`;
   - `options`: `temperature 0.2`, `num_ctx 8192`.
2. Timeout `config.REQUEST_TIMEOUT = 2400` saniyədir (40 dəqiqə). Bu, **hər bir HTTP sorğusu üçündür**, bütün iş üçün deyil. Məsələn, `--split` ilə 10 qeyd `1 + 2×10 = 21` sorğu deməkdir və hər biri ayrıca 40 dəqiqəyə qədər gözləyə bilər.
3. Cavab: `r.json()["response"]` → `_extract_json` → `dict`. Validation və retry API rejimi ilə eynidir.
4. Ollama yoxlaması API rejimindəki kimidir, yəni yalnız embedding modeli yoxlanır. `qwen3:14b`-nin yüklü olub-olmadığı **yoxlanmır**. Model yoxdursa, ilk generate sorğusu HTTP xətası verir və heç nə yazılmır.
5. Giriş və çıxış birlikdə `num_ctx` (8192 token) həddini keçəndə nə baş verdiyini Ollama müəyyən edir. Bunu yoxlamadım.

### B.7. `kb --reindex` (texniki baxım; altı rejimə əlavə olaraq)

1. Ollama yoxlamasından sonra `handle_reindex()` çağırılır (`engine/cli.py:279-281`, `236-265`).
2. `find_index_drift()` (`engine/main.py:93-110`) yalnız oxuyur:
   - `list_all_notes()` ilə diskin xəritəsini qurur: `{slug: [kateqoriyalar]}`;
   - index ilə müqayisə edir və dörd siyahı qaytarır: `missing_file`, `wrong_category`, `not_indexed`, `duplicate`.
   - `find_note`-dan istifadə **etmir**, ona görə dublikat olanda da işləyir.
3. `check_layout()` (`engine/vault.py:9-18`) çatışmayan və iç-içə kateqoriya qovluqlarını xəbərdarlıq kimi göstərir.
4. Dəyişiklik yoxdursa: `Index matches the vault. Nothing to repair.`
5. Əks halda `Apply these changes to the index? (yes/no)` soruşulur. `yes` olarsa, `repair_index(drift)` çağırılır (`engine/main.py:113-126`):
   1. **[EMB]** Index-də olmayan qeydlər üçün **əvvəl** bütün embedding-lər alınır. Fayl `markdown_to_json` ilə oxunur, başlıq boşdursa slug istifadə olunur.
   2. **[VAULT]** Sonra index **bir dəfə** yazılır: ghost yazılar silinir, kateqoriyalar diskə uyğunlaşdırılır, yeni yazılar əlavə olunur.
   3. Dublikatlara toxunulmur.
   4. Qeyd fayllarına heç vaxt toxunulmur.

---

## C. Modul arayışı

### C.1. `engine/config.py`: bütün tənzimləmələr

**Vəzifəsi:** sabitləri bir yerdə saxlamaq. Funksiyası yoxdur. İmport olunanda bir dəfə hesablanır.

| Sabit | Sətir | Dəyər | Kim oxuyur |
|---|---|---|---|
| `VAULT` | 5 | `CKE_VAULT` və ya `~/Documents/CyberKB` | `vault.py`, `main.repair_index` |
| `INDEX_FILE` | 6 | `VAULT / ".kb_index.json"` | `memory.py` |
| `CLASSIFIER_CATEGORIES` | 10-13 | 10 kateqoriya (`00`–`09`) | `brain.choose_category`, `vault.check_layout` |
| `VAULT_CATEGORIES` | 16 | yuxarıdakılar + `90`, `91`, `99` (13) | `vault.category_dirs`, `vault.check_layout` |
| `OLLAMA_BASE` / `_GEN` / `_EMB` | 18-20 | `http://localhost:11434...` | `cli.check_ollama`, `llm` |
| `CHAT_MODEL` | 22 | `qwen3:14b` | `llm._ask_json_local` |
| `EMBED_MODEL` | 23 | `nomic-embed-text` (tag-sız, Ollama özü `:latest` əlavə edir) | `llm.embed`, `cli.check_ollama` |
| `CANDIDATE_THRESHOLD` | 25 | `0.60` | `memory.find_top_matches` |
| `MAX_RETRIES` | 26 | `2` (cəmi 3 cəhd) | `brain.generate_validated` |
| `NUM_CTX` | 27 | `8192` | `llm._ask_json_local` |
| `REQUEST_TIMEOUT` | 28 | `2400` s, **hər Ollama sorğusu üçün** | `llm._ask_json_local` |
| `DEFAULT_BACKEND` | 32 | `"api"` | `cli.run`, `llm.ask_json` (`backend=None` olanda) |
| `SERVER_HOST` / `SERVER_PORT` | 37-38 | `127.0.0.1` / `8000` | `server.py` |
| `API_BASE_URL` / `API_MODEL` / `API_TIMEOUT` | 41-43 | DeepSeek / `deepseek-flash` / `600` s | `llm.get_api_client`, `llm._ask_json_api` |

**Diqqət ediləcək cəhətlər:**

- `CKE_VAULT` boşdursa, defolt yol götürülür (`or`). Dırnaq içində `~` yazılsa da açılır (`expanduser`). `.env`-dən oxunmur (B.0, addım 2).
- "Bütün tənzimləmələr config-dədir" qaydasının **istisnaları:**
  - `llm.embed`-in timeout-u `60` saniyədir (`engine/llm.py:30`);
  - `cli.check_ollama`-nın timeout-u `5` saniyədir (`engine/cli.py:19`);
  - `temperature 0.2`, `top_p 0.95`, `max_tokens 32768` dəyərləri `llm.py`-də birbaşa yazılıb.

  Bunlar təmirdən əvvəl də belə idi və dəyişdirilmədi.

### C.2. `engine/schema.py`: modelin cavabının forması

**Vəzifəsi:** LLM-dən gələn `dict`-i yoxlamaq və tipli obyektə çevirmək. Pydantic v2 istifadə olunur.

**`Section`** (`4-45`): `heading: str`, `content: str`.

| Validator | Sətir | Nə edir |
|---|---|---|
| `accept_title_as_heading` (before) | 8-16 | `heading` yoxdursa `title`-ı, `content` yoxdursa `body`-ni götürür. Model bəzən başqa açar adları qaytarır |
| `heading_not_empty` | 18-23 | Boş başlığı rədd edir və `strip` edir |
| `content_to_string` (before) | 25-38 | `str` olduğu kimi keçir. `list[str\|int\|float]` hər elementi `- ` ilə başlayan bullet sətrinə çevirir. `None`, `dict`, `bool`, tək rəqəm və iç-içə list `ValueError` verir |
| `content_not_empty` | 40-45 | Boş məzmunu rədd edir və `strip` edir. `[]` boş sətir verdiyi üçün burada rədd olunur |

**`PlanEntry`** (`48-60`): `title: str` məcburidir və boş ola bilməz. `type`, `covers`, `source_hint` istəyə bağlıdır, defolt `""`. `None` gəlsə, `ValidationError` olur və retry başlayır.

**`SplitPlan`** (`63-64`): `notes: list[PlanEntry]`. `notes` açarı yoxdursa və ya siyahı deyilsə, `ValidationError`.

**`Note`** (`67-92`): `title`, `summary`, `sections: list[Section]`.

| Validator | Sətir | Nə edir |
|---|---|---|
| `fill_missing_summary` (before) | 72-78 | `summary` boşdursa, `title` ilə doldurur |
| `not_empty` | 80-85 | `title` və `summary` boş ola bilməz. `strip` edir |
| `at_least_one_section` | 87-92 | Ən azı bir bölmə olmalıdır |

**Kim istifadə edir:** `brain.py` (`Note`, `SplitPlan`) və testlər. `main.process_from_plan` `note.title`-ı sonradan dəyişir (`engine/main.py:161`). Pydantic-də `validate_assignment` defolt olaraq söndürülüb, ona görə bu təyin etmə yoxlanmır. Amma həmin başlıq artıq `PlanEntry`-də yoxlanıb.

**Gözlənilməz cəhət:** `bool` `int`-in alt sinfidir, ona görə `content_to_string`-də ayrıca istisna olunur (`engine/schema.py:34-35`).

### C.3. `engine/vault.py`: disk üzərində qeydlər

**Vəzifəsi:** qeyd fayllarını tapmaq, oxumaq, yazmaq və silmək, slug yaratmaq, Markdown ↔ dict çevirmək. LLM ilə işləmir.

| Funksiya | Sətir | Qaytarır | Kim çağırır | Kimi çağırır |
|---|---|---|---|---|
| `category_dirs()` | 4-6 | Mövcud kateqoriya qovluqlarının `Path` siyahısı, `config` sırası ilə | `check_layout`, `find_note`, `main.list_all_notes` | — |
| `check_layout()` | 9-18 | `(missing, nested)`: yuxarıda olmayan classifier kateqoriyaları və `"03 Windows/02 Linux"` kimi iç-içə qovluqlar | `cli.handle_reindex` | `category_dirs` |
| `NoteExistsError(slug, category)` | 21-27 | `RuntimeError`-un alt sinfi. Yazı mövcud qeydi əvəz edəcəkdisə qalxır. `.slug` və `.category` daşıyır | `ensure_new`, `write_note` | — |
| `find_note(slug)` | 30-42 | `(Path, kateqoriya)` və ya `(None, None)`. Slug iki yerdədirsə, `RuntimeError` | `read_note`, `ensure_new`, `write_note`, `delete_note`, `main.merge_into`, `main.delete_note_by_slug`, `server.add_note` | `category_dirs` |
| `read_note(slug)` | 45-49 | Faylın mətni və ya `""` | `main.merge_into`, `cli.report_existing` | `find_note` |
| `ensure_new(slug)` | 52-56 | `None`. Slug artıq varsa, `NoteExistsError` | `main.process`, `main.process_from_plan` | `find_note` |
| `write_note(slug, category, markdown, replace=False)` | 59-70 | `None`. Slug artıq varsa və `replace=False`-dursa, `NoteExistsError`. Əks halda faylı yazır, slug başqa kateqoriyada idisə köhnəsini silir | `main.save_note` | `find_note` |
| `delete_note(slug)` | 73-76 | `None`. Faylı silir, fayl yoxdursa heç nə etmir | `main.merge_into`, `main.delete_note_by_slug` | `find_note` |
| `slugify(title, fallback=True)` | 79-94 | Slug `str` | `main.process`, `merge_into` (`fallback=False`), `process_from_plan`, `process_writeup`, `cli.handle_split` | `re`, `hashlib` |
| `to_markdown(note)` | 97-104 | Markdown `str` | `main.save_note` | — |
| `markdown_to_json(markdown)` | 107-139 | `{"title", "summary", "sections"}` dict-i | `main.merge_into`, `main.repair_index`, `cli.report_existing` | — |

**Diqqət ediləcək cəhətlər:**

- **`slugify`** addımları:
  1. kiçik hərfə çevirir;
  2. `a-z0-9`, boşluq və `-`-dən başqa hər şeyi silir (nöqtə və `/` də daxil);
  3. boşluqları `-` ilə əvəz edir;
  4. ilk 8 sözü saxlayır.

  Nəticə boşdursa və `fallback=True`-dursa, `untitled-<sha256(title)[:8]>` qaytarır. Bu, deterministikdir: eyni başlıq həmişə eyni ad verir. Qeyri-latın hərflər silinir, məsələn `"Café"` → `"caf"`. Bu davranış qəsdən dəyişdirilmədi, çünki mövcud fayl adları dəyişərdi.
- **`markdown_to_json`** bir vəziyyət dəyişəni (`fence`) ilə işləyir:
  - Sətrin girintisiz ilk 3 simvolu ```` ``` ```` və ya `~~~`-dirsə, fence açılır.
  - Fence yalnız **eyni** marker ilə bağlanır.
  - Fence-in içindəki hər sətir, fence sətirləri də daxil, cari bölmənin məzmununa olduğu kimi düşür.
  - Başlığı yalnız birinci `# ` sətri təyin edir, sonrakı `# ` sətirləri məzmundur.
  - Birinci `## `-dən əvvəlki boş olmayan sətirlər bir sətirlik `summary`-yə birləşdirilir. Ona görə preambula çox sətirli olsa, round-trip-də bir sətrə düşür.
  - **Sadələşdirmə:** CommonMark-ın "bağlayan fence açandan qısa olmamalı və info string-i olmamalıdır" qaydası tətbiq olunmayıb. Real vault-da bu fərq heç bir qeyddə rol oynamır.
- **`write_note`** defolt olaraq mövcud qeydi əvəz etmir (`NoteExistsError`, P0-3). `replace=True`-nu yalnız `merge_into` verir, o da yalnız birləşdirilən qeydin öz slug-ı üçün. Bu halda "əvvəl yaz, sonra köhnəni sil" qaydası işləyir.
- **`find_note`-un dublikatda xəta verməsi** bilərəkdəndir: oxuma, yazma, silmə və merge səhv nüsxəni təxmin etmir, dayanır.

### C.4. `engine/memory.py`: embedding index-i

**Vəzifəsi:** `.kb_index.json`-u oxumaq və yazmaq, oxşar qeydləri tapmaq.

| Funksiya | Sətir | Qaytarır | Kim çağırır | Kimi çağırır |
|---|---|---|---|---|
| `load_index()` | 5-8 | `dict`. Fayl yoxdursa `{}` | `save_entry`, `remove_entry`, `find_top_matches`, `main.find_index_drift`, `main.repair_index`, `cli.handle_reindex` | — |
| `save_index(index)` | 11-12 | `None`. Bütün index-i bir sətirlik JSON kimi yazır (`ensure_ascii=False`) | `save_entry`, `remove_entry`, `main.repair_index` | — |
| `similarity(a, b)` | 15-21 | Cosine similarity `float`. Vektorlardan biri sıfırdırsa `0.0` | `find_top_matches` | — |
| `embed_entry(title, summary, category="00 Inbox")` | 24-30 | `{"vector", "title", "category"}`. **Şəbəkə addımıdır** | `main.save_note`, `main.repair_index` | `llm.embed` |
| `save_entry(slug, entry)` | 33-36 | `None`. Index-i oxuyur, yazını əlavə edir, yenidən yazır | `main.save_note` | `load_index`, `save_index` |
| `remove_entry(slug)` | 38-42 | `None`. Slug yoxdursa heç nə etmir | `main.merge_into`, `main.delete_note_by_slug` | `load_index`, `save_index` |
| `find_top_matches(text, limit=5)` | 45-56 | `[(slug, title, category, score)]`. `>= 0.60` olanlar, azalan sıra ilə | `main.find_merge_candidates` | `load_index`, `llm.embed`, `similarity` |

**Diqqət ediləcək cəhətlər:**

- `embed_entry` və `save_entry` təmir zamanı köhnə `update_entry`-nin iki hissəyə bölünməsindən yaranıb (P1-4). Məqsəd şəbəkə addımını disk addımından ayırmaqdır ki, `main.save_note` onları düzgün sıra ilə çağıra bilsin.
- Embedding üçün mətn `"{title}\n{summary}"`-dir, yəni bölmələrin məzmunu embedding-ə **daxil deyil**.
- **Sadələşdirmə:** hər yazma bütün index-i (təxminən 0.9 MB) oxuyub yenidən yazır. Yazma atomik deyil, müvəqqəti fayl və `rename` istifadə olunmur. 55 qeyd üçün sürət problemi yoxdur. Amma yazma yarıda kəsilsə, fayl korlana bilər (I bölməsi).
- Cosine similarity saf Python ilə hesablanır və `numpy` istifadə olunmur, çünki yeni dependency qadağandır. 55 × 768 ölçü üçün bu kifayətdir.

### C.5. `engine/llm.py`: modellərlə əlaqə

**Vəzifəsi:** chat sorğusunu seçilmiş backend-ə göndərmək və cavabdan JSON çıxarmaq; Ollama-dan embedding almaq. Bu modul validation etmir, o iş `brain.py`-dədir.

| Funksiya / ad | Sətir | Qaytarır | Kim çağırır |
|---|---|---|---|
| `PROJECT_ROOT`, `load_dotenv(...)` | 9-10 | Import zamanı `~/cke/.env` yüklənir | — |
| `get_api_client()` | 15-22 | `OpenAI` client-i. Tək nüsxədir (singleton), ilk çağırışda yaradılır. Açar yoxdursa `RuntimeError` | `_ask_json_api` |
| `embed(text)` | 25-33 | 768 `float`. Mətn 6000 simvola qədər kəsilir, timeout 60 s | `memory.embed_entry`, `memory.find_top_matches` |
| `_ask_json_local(system, prompt)` | 36-53 | `dict`. Ollama `/api/generate` | `ask_json` |
| `_ask_json_api(system, prompt)` | 56-70 | `dict`. DeepSeek chat completions | `ask_json` |
| `_extract_json(raw)` | 73-78 | `dict`. Birinci `{` ilə sonuncu `}` arasını kəsir və `json.loads` edir | `_ask_json_local`, `_ask_json_api` |
| `ask_json(system, prompt, backend=None)` | 81-86 | `dict`. `backend=None` olanda `config.DEFAULT_BACKEND` götürülür | `brain.generate_validated`, `brain.choose_category` |

**Diqqət ediləcək cəhətlər:**

- DeepSeek API OpenAI ilə uyğundur, ona görə `openai` paketi `base_url=https://api.deepseek.com` ilə işlədilir.
- `_extract_json` modelin JSON-dan əvvəl və ya sonra yazdığı adi mətni atır. Amma həmin mətndə özündə `{` və ya `}` varsa, kəsilən hissə JSON olmur və `json.loads` uğursuz olur. Bu zaman `brain`-dəki retry işə düşür. F bölməsində ətraflı izah var.
- Server `process(text)`-i `backend=None` ilə çağırır. Server-in hansı modeldən istifadə etdiyi buradakı defolt qoldan asılıdır.

### C.6. `engine/brain.py`: prompt-lar və validation döngüsü

**Vəzifəsi:** hər iş üçün prompt saxlamaq və modelin cavabını schema-ya uyğun olana qədər (ən çox 3 cəhd) yenidən soruşmaq.

| Funksiya | Sətir | Qaytarır | Kim çağırır | Kimi çağırır |
|---|---|---|---|---|
| `generate_validated(system, prompt, backend=None, schema=Note)` | 112-124 | `schema` obyekti: `Note` və ya `SplitPlan` | aşağıdakı dörd funksiya | `llm.ask_json`, `schema.model_validate` |
| `create_note(text, backend=None)` | 127-128 | `Note` | `main.process`, `main.merge_into`, `main.process_from_plan` | `generate_validated(CREATE_SYSTEM, ...)` |
| `merge_two_notes(existing_json, new_json, backend=None)` | 131-133 | `Note` | `main.merge_into` | `generate_validated(MERGE_SYSTEM, ...)` |
| `choose_category(title, summary, backend=None)` | 156-165 | Kateqoriya `str`. Həmişə `CLASSIFIER_CATEGORIES`-dən biridir | `main.process`, `main.process_from_plan` | `llm.ask_json(CATEGORY_SYSTEM, ...)` |
| `propose_split(text, backend=None)` | 203-206 | Plan dict-lərinin siyahısı | `main.propose_split_plan` | `generate_validated(SPLIT_SYSTEM, ..., schema=SplitPlan)` |
| `create_writeup(text, backend=None)` | 247-248 | `Note` | `main.process_writeup` | `generate_validated(WRITEUP_SYSTEM, ...)` |

Prompt sabitləri: `TITLE_RULE` (6-16), `VALUE_HANDLING` (18-31), `CREATE_SYSTEM` (33-78), `MERGE_SYSTEM` (80-109), `CATEGORY_SYSTEM` (135-153), `SPLIT_SYSTEM` (169-200), `WRITEUP_SYSTEM` (211-244). Onların məzmunu E bölməsindədir.

**Diqqət ediləcək cəhətlər:**

- `generate_validated` yalnız `ValidationError`, `ValueError` və `json.JSONDecodeError`-u tutub retry edir. Şəbəkə, auth və `RuntimeError` (məsələn açar yoxdursa) dərhal yuxarı ötürülür.
- Retry prompt-u orijinal prompt-a bu cümləni əlavə edir: `"Your previous response was rejected: <xəta>\nFix it and respond with valid JSON only."` Hər cəhddə bu, orijinal prompt-a əlavə olunur, əvvəlki cəhdlərin xətaları yığılmır.
- `choose_category` heç vaxt xəta qaldırmır: istənilən problemdə `"00 Inbox"` qaytarır. Bu, qəsdəndir, çünki səhv kateqoriya qeydin itməsindən yaxşıdır.
- Təmir zamanı `decide_same_topic` və `DECISION_SYSTEM` silindi (P2-3), qalan prompt mətnləri dəyişmədi.

### C.7. `engine/main.py`: iş axınları

**Vəzifəsi:** `brain`, `vault` və `memory`-ni hər rejim üçün düzgün sıra ilə birləşdirmək. İstifadəçi ilə danışmır və `input()` çağırmır. Bu iş `cli.py`-dədir.

| Funksiya | Sətir | Qaytarır | Kim çağırır | Kimi çağırır |
|---|---|---|---|---|
| `save_note(slug, category, note, replace=False)` | 4-9 | `None`. Sıra: embedding → fayl → index | `process`, `merge_into`, `process_from_plan`, `process_writeup` | `memory.embed_entry`, `vault.write_note`, `vault.to_markdown`, `memory.save_entry` |
| `process(text, backend=None)` | 12-26 | slug. Slug artıq varsa, `NoteExistsError` | `cli.run`, `server.add_note`, `__main__` | `brain.create_note`, `vault.slugify`, `vault.ensure_new`, `brain.choose_category`, `save_note` |
| `find_merge_candidates(text)` | 29-30 | Namizəd siyahısı | `cli.run` | `memory.find_top_matches` |
| `merge_into(text, target_slug, backend=None, confirm_rename=None)` | 33-71 | Son slug | `cli.run` | `vault.read_note`, `markdown_to_json`, `find_note`, `brain.create_note`, `brain.merge_two_notes`, `vault.slugify(fallback=False)`, `confirm_rename`, `save_note`, `vault.delete_note`, `memory.remove_entry` |
| `list_all_notes()` | 73-79 | `[(slug, category)]` | `notes_on_disk`, `cli.handle_delete`, `cli.handle_reindex` | `vault.category_dirs` |
| `notes_on_disk()` | 82-90 | `{slug: [kateqoriyalar]}`. Dublikatda xəta vermir | `find_index_drift`, `cli.handle_split` | `list_all_notes` |
| `find_index_drift()` | 93-110 | 4 açarlı dict (B.7-yə baxın) | `cli.handle_reindex` | `memory.load_index`, `notes_on_disk` |
| `repair_index(drift)` | 113-126 | `None` | `cli.handle_reindex` | `markdown_to_json`, `memory.embed_entry`, `load_index`, `save_index` |
| `delete_note_by_slug(slug)` | 129-135 | slug. Tapılmasa `RuntimeError` | `cli.handle_delete` | `vault.find_note`, `vault.delete_note`, `memory.remove_entry` |
| `propose_split_plan(text, backend=None)` | 137-138 | Plan | `cli.handle_split` | `brain.propose_split` |
| `process_from_plan(text, note_plan, backend=None)` | 140-164 | `(slug, category)`. Slug artıq varsa, model çağırılmadan `NoteExistsError` | `cli.handle_split` | `slugify`, `ensure_new`, `brain.create_note`, `choose_category`, `save_note` |
| `process_writeup(text, backend=None)` | 166-173 | slug | `cli.run` | `brain.create_writeup`, `slugify`, `save_note` |
| `__main__` bloku | 175-181 | — | `python -m engine.main "mətn"` | `process`. Ollama əvvəlcədən yoxlanmır, backend defoltdur |

**Diqqət ediləcək cəhətlər:**

- `save_note` P1-4-dən gəlir. Dörd yaradılış yolu eyni sıranı paylaşır və sıra yalnız bir yerdə izah olunur.
- Yaradılış yolları (`process`, `process_from_plan`, `process_writeup`) `replace` vermir, ona görə mövcud qeydi heç vaxt əvəz etmir (P0-3). `process` bunu kateqoriya çağırışından əvvəl, `process_from_plan` isə heç bir model çağırışından əvvəl yoxlayır.
- `merge_into`-nun `confirm_rename` parametri callback-dir. `None` olanda, məsələn server-də və ya testdə, fayl adı dəyişmir.
- `merge_into`-da **əvvəl yazılır, sonra silinir**. Proses yarıda qırılsa, iki fayl qalar, amma heç biri itməz.
- `find_index_drift` `find_note`-u çağırmır (B.7).
- **`list_all_notes` funksiyasının ətrafında boş sətir sayı PEP 8-ə tam uyğun deyil** (bəzi funksiyalar arasında bir boş sətir var). Bu, təmirdən əvvəl də belə idi.

### C.8. `engine/cli.py`: terminal interfeysi

**Vəzifəsi:** arqumentləri oxumaq, istifadəçidən mətn və təsdiq almaq, spinner göstərmək və xətaları `ERROR: ...` kimi çap etmək.

| Funksiya / sinif | Sətir | Qaytarır | Kim çağırır |
|---|---|---|---|
| `with_tag(model)` | 11-13 | Tag-ı olmayan ada `:latest` əlavə edir | `check_ollama` |
| `check_ollama()` | 16-25 | `bool`: HTTP 200 qaytarılıb və embedding modeli var | `require_ollama`; testlər |
| `require_ollama()` | 28-32 | Uğursuz olanda `sys.exit(1)` | `run` |
| `confirm_rename(old_slug, new_slug)` | 35-41 | `bool`. TTY yoxdursa `False` | `run` (`ask_rename` vasitəsilə) |
| `report_existing(error)` | 44-52 | `None`. Adi `kb` dayananda mövcud qeydin başlığını, kateqoriyasını və yolunu göstərir, `kb --merge` təklif edir | `run` |
| `get_input_text(args)` | 55-70 | `str`: `--file` faylı, arqumentlər və ya `stdin` | `run` |
| `Spinner` | 73-98 | Ayrı thread-də `\|/-\` animasiyası. `start()`, `stop()` | `run`, `handle_split` |
| `handle_split(backend, text)` | 100-199 | `None` | `run` |
| `handle_delete()` | 201-233 | `None` | `run` |
| `handle_reindex()` | 236-265 | `None` | `run` |
| `run()` | 268-389 | `None` və ya `sys.exit(1)` | `__main__` (`python -m engine.cli`) |

**`run()`-un sırası:**

1. `--delete`;
2. `require_ollama()`;
3. `--reindex`;
4. backend (`--local`);
5. `--split`;
6. `--writeup`;
7. `--merge` flag-ı;
8. mətn və onun uzunluğu;
9. merge axını və ya adi yaradılış.

**Diqqət ediləcək cəhətlər:**

- `--file` yalnız flag-lar silindikdən sonra **ilk qalan arqument** olanda tanınır (`engine/cli.py:56`). `kb --split --file x.md` və `kb --file x.md --merge` işləyir, çünki flag-lar istənilən yerdən silinir.
- Rename sualı verilməzdən əvvəl spinner dayandırılır (`ask_rename`, `engine/cli.py:357-359`). Əks halda spinner-in `\r` yazıları sualın üstünə düşərdi.
- `handle_split`-də plan elementləri `dict`-dir. CLI-ın özünün yaratdığı birləşdirilmiş element də `dict`-dir (`engine/cli.py:162-163`).
- Uzunluq hədləri: adi `kb` və `--merge` üçün 30, `--split` və `--writeup` üçün 100 simvol. Qısa mətndə adi `kb` `exit(1)` edir, `--split` və `--writeup` isə sadəcə qayıdır.

### C.9. `engine/server.py`: köhnə (legacy) HTTP server

**Vəzifəsi:** `POST /note` ilə gələn mətndən adi qeyd yaratmaq. `--split` və `--writeup` dəstəklənmir.

| Ad | Sətir | Nə edir |
|---|---|---|
| `TOKEN` | 10 | `CKE_SERVER_TOKEN` (`.env` artıq `llm.py` tərəfindən yüklənib) |
| `LOCAL_ONLY` | 11 | `SERVER_HOST` `127.0.0.1`, `localhost` və ya `::1`-dirsə `True` |
| `authorized()` | 14-20 | Localhost-da həmişə `True`. Əks halda `Authorization: Bearer <token>` `hmac.compare_digest` ilə yoxlanır. `TOKEN` boşdursa heç nə qəbul olunmur |
| `health()` | 23-25 | `GET /health` → `{"status": "ok"}`. Token tələb etmir |
| `add_note()` | 28-48 | `POST /note`: əvvəl icazə yoxlanır (401), sonra `text` (30 simvoldan qısadırsa 400), sonra `process(text)`, sonra `find_note`-dan kateqoriya götürülür. Exception olarsa 500 |
| `__main__` | 51-59 | Banner çap edir və `app.run(host=SERVER_HOST, port=SERVER_PORT)` |

**Diqqət ediləcək cəhətlər:**

- Server `cli.require_ollama()`-ni çağırmır. Ollama sönülü olanda DeepSeek çağırışları edilir, sonra `save_note`-un embedding addımı uğursuz olur. Heç bir fayl yazılmır, amma API xərci gedir.
- Public rejimdə token yoxdursa, server dayanmır, hər `/note`-u 401 ilə rədd edir. Səbəb: launchd `KeepAlive` çıxan server-i hər dəfə yenidən başladardı və log dolardı.
- `server.log`-u launchd açır (`StandardOutPath`/`StandardErrorPath`). Rotation manualdır: `mv server.log ...`, sonra `launchctl kickstart -k gui/$(id -u)/com.cke.server`.
- Flask-ın development server-i istifadə olunur. Werkzeug log-da "Do not use it in a production deployment" xəbərdarlığını çap edir.

### C.10. Digər fayllar

- **`engine/__init__.py`**: boşdur (0 bayt). Yalnız `engine` qovluğunu Python paketi kimi işarələyir ki, `python -m engine.cli` və `from engine import ...` işləsin.
- **`kb`** (4 sətir): `cd ~/cke`, `source venv/bin/activate`, `python3 -m engine.cli "$@"`. `~/cke` yolu skriptin içində birbaşa yazılıb, ona görə repo başqa yerə clone edilsə, skript də dəyişdirilməlidir.
- **`kb-local.sh`**: təmir zamanı silindi (`9b4d2f8`). Heç yerdən çağırılmırdı. Onun `nano` açma funksiyasını indi `kb --file <path>` əvəz edir.
- **`tests/test_cke.py`** (811 sətir, 70 test) və **`tests/fixtures/`** (4 sintetik qeyd):
  - **Təhlükəsizlik qurğusu** (`30-41`):
    - `REAL_VAULT` istifadəçinin başlanğıcdakı `CKE_VAULT` dəyəridir;
    - `TEST_VAULT` müvəqqəti qovluqdur;
    - `os.environ["CKE_VAULT"]` engine import olunmazdan **əvvəl** dəyişdirilir;
    - `config.VAULT` müvəqqəti qovluğa bərabər deyilsə, test dəsti işə düşmür.
  - **Köməkçilər:**
    - `fake_embed` (50): saxta vektor;
    - `make_note` (54): test üçün `Note`;
    - `outline` (62): qeydin başlığını, `##` başlıqlarını və kod sətirlərini **müstəqil** oxuyur. Round-trip testlərində gözlənilən nəticə budur;
    - `FakeResponse` (86): `check_ollama` üçün saxta HTTP cavabı;
    - `VaultTestCase` (97): hər test üçün boş vault yaradır, `llm.embed`-i saxta funksiya ilə əvəz edir, `llm.ask_json`-u bloklayır (model çağırılarsa test sınır), `stdout`-u tutur.
  - **Test sinifləri bəndlərə görə adlandırılıb:**
    - `P0_1_ParserTests` (143), `P0_1_RealVaultRoundTrip` (181, yalnız `CKE_VAULT` təyin olunanda işləyir, vault-dan yalnız oxuyur), `P0_1_MergeSafetyTests` (203);
    - `P0_2_DuplicateSlugTests` (270), `P0_3_NoOverwriteTests` (313);
    - `P1_1_ReindexTests` (421), `P1_2_CategoryFolderTests` (488), `P1_3_LayoutCheckTests` (521);
    - `P1_4_OllamaCheckTests` (538), `P1_4_CliChecksOllamaFirstTests` (565), `P1_4_NoUnindexedNoteTests` (596);
    - `P1_5_SectionContentTests` (643), `P1_6_SlugifyTests` (690);
    - `P2_1_SplitPlanTests` (722), `P2_4_DefaultBackendTests` (759), `P2_6_ServerAuthTests` (780).
  - **İşə salmaq:** `cd ~/cke && source venv/bin/activate && python -m unittest discover -s tests -v`. Real vault yoxlaması da lazımdırsa, əvvəlinə `CKE_VAULT=~/Documents/CyberKB` əlavə edin. Python 3.11+ tələb olunur (`enterContext`).
  - **Fixture-lar** HTB materialı deyil, əl ilə yazılmış qısa nümunələrdir:
    - `code_comment.md`: kod blokunda `#` şərhi;
    - `tilde_fence.md`: `~~~` fence-i və onun içində `##`;
    - `second_h1.md`: ikinci `# ` və girintili fence;
    - `nested_fence.md`: `~~~` içində ```` ``` ````.

---

## D. Məlumat formaları (diskdə və yaddaşda dəqiq nə var)

### D.1. Qeydin Markdown forması

`vault.to_markdown` (`engine/vault.py:97-104`) bu formanı yaradır:

```text
# <title>

<summary>

## <heading 1>

<content 1>

## <heading 2>

<content 2>

```

Hər element arasında bir boş sətir var, fayl `\n` ilə bitir. Ön məlumat bloku (YAML front matter) və teqlər yoxdur. `content`-in içində ``` fence-ləri və `###` alt başlıqları ola bilər. Parser bunları bölmənin məzmunu sayır.

`markdown_to_json` əks istiqamətdə `{"title": str, "summary": str, "sections": [{"heading": str, "content": str}]}` qaytarır. Round-trip başlığı, `##` başlıqlarını və kod bloklarının hər sətrini saxlayır. Bunu real vault-da 55/55 nəticəsi təsdiqləyir. Yalnız çox sətirli preambula bir sətirlik `summary`-yə birləşir.

### D.2. Pydantic modelləri

```text
Section    heading: str (boş olmaz)
           content: str (boş olmaz; giriş str və ya list[str|int|float] ola bilər)
           aliaslar: "title" → heading, "body" → content

Note       title: str (boş olmaz)
           summary: str (boş olmaz; yoxdursa title-dan doldurulur)
           sections: list[Section] (ən azı 1)

PlanEntry  title: str (boş olmaz)
           type, covers, source_hint: str (defolt "")

SplitPlan  notes: list[PlanEntry]
```

**Rədd edilən hallar** (hər biri `ValidationError` verir və retry başlayır):
- boş başlıq, boş məzmun, sıfır bölmə;
- `content` olaraq `None`, `dict`, `bool`, tək rəqəm və ya iç-içə list;
- başlığı olmayan plan elementi;
- `notes` açarının olmaması və ya onun siyahı olmaması.

### D.3. `.kb_index.json`

Vault-un kökündədir, bir sətirlik JSON-dur (`ensure_ascii=False`):

```json
{
  "nmap": {
    "vector": [0.0123, -0.0456, "... cəmi 768 float ..."],
    "title": "Nmap",
    "category": "08 Tools"
  }
}
```

- **Açar yalnız slug-dur.** Kateqoriya açarın bir hissəsi deyil. Ona görə eyni slug-u iki kateqoriyada saxlamaq mümkün deyil (P0-2).
- **Vektorlar `nomic-embed-text` modelindən gəlir və 768 ölçülüdür.** Embedding mətni `"{title}\n{summary}"`-dir.
- **`summary` sahəsi yoxdur.** Index yalnız `vector`, `title`, `category` saxlayır. Silinmiş `decide_same_topic`-i qoşmaq çətin olmasının səbəbi də budur.
- Hazırda 55 yazı var, faylın ölçüsü təxminən 0.9 MB-dır.

### D.4. `--split` planının elementi

Model bu formada qaytarır, `SplitPlan` yoxlayır, `propose_split` isə dict kimi ötürür:

```json
{"title": "Subdomain Enumeration", "type": "technique", "covers": "one short sentence", "source_hint": "which heading(s)"}
```

`type` prompt-da `"tool | technique | concept"` kimi təsvir olunub, amma kod onun dəyərini yoxlamır, istənilən string qəbul olunur. CLI-da birləşdirilmiş element həmişə `"type": "technique"` alır.

### D.5. `.env`

`~/cke/.env` faylıdır, git-ə düşmür (`.gitignore`). `engine/llm.py:10` onu yükləyir.

```bash
DEEPSEEK_API_KEY=...        # API backend üçün məcburidir
CKE_SERVER_TOKEN=...        # istəyə bağlı; yalnız SERVER_HOST localhost deyilsə lazımdır
```

`CKE_VAULT` buraya yazılsa **işləməz**. O, shell mühit dəyişəni olmalıdır, məsələn `~/.zshrc`-də `export` ilə.

---

## E. Prompt-lar (`engine/brain.py`)

Bu bölmədə hər prompt-un nə üçün olduğu, içindəki əsas göstərişlər və onların niyə belə yazıldığı izah olunur. Prompt mətnləri uzun tənzimləmənin nəticəsidir və təmir zamanı dəyişdirilmədi. Silinən yeganə prompt `DECISION_SYSTEM`-dir (P2-3).

Prompt-lar bir-birindən hissə götürür. `CREATE_SYSTEM` və `MERGE_SYSTEM` `TITLE_RULE` və `VALUE_HANDLING`-i string birləşdirməsi ilə öz içinə qoşur (`engine/brain.py:39`, `86`). `WRITEUP_SYSTEM` isə bunları qoşmur, onun öz `VALUE HANDLING` hissəsi var.

### E.1. `TITLE_RULE` (6-16)

- **Vəzifəsi:** başlığın necə olmalı olduğunu müəyyən etmək.
- **Əsas göstərişlər:**
  - başlıq standart terminlə başlayan, 2–5 sözlük ad olmalıdır;
  - iki nöqtədən sonra alt mövzu siyahısı olmamalıdır;
  - çox çılpaq ("Scanning") və çox uzun başlıqların nümunələri verilib.
- **Niyə belədir:** başlıqdan slug yaranır (`slugify`, 8 sözlə məhdudlaşır) və qeyd sonra başlığa görə axtarılır. Qısa və sabit başlıq fayl adını da sabit saxlayır. Bu, merge-də rename riskini azaldır.

### E.2. `VALUE_HANDLING` (18-31): placeholder siyasəti

- **Vəzifəsi:** nəyin olduğu kimi saxlanacağını, nəyin placeholder-ə (yer tutucuya) çevriləcəyini müəyyən etmək.
- **Olduğu kimi saxlanılanlar (PRESERVE EXACTLY):** hücum addımları, məntiq, əmrlərin strukturu, endpoint nümunələri, parametr adları, HTTP metodları, səhv mesajlarının mənası və hər addımın **niyə** işlədiyi.
- **Placeholder-ə çevrilənlər:**
  - birdəfəlik dəyərlər: `uuid`, id, hash, token → `<uuid>`, `<hash>`, `<token>`;
  - labdakı adlar və email-lər → `<username>`, `<email>`;
  - lab maşınının IP ünvanı → `<target_ip>`;
  - `HTB{...}` flag-ları tamamilə atılır.
- **Qadağa:** uydurma, "real kimi görünən" dəyər yazmaq olmaz, məsələn `new-uuid-1234`. Real dəyər yoxdursa, aydın `<placeholder>` yazılmalıdır.
- **Niyə belədir:** ensiklopediya metodologiyanı saxlayır, bir dəfəlik lab dəyərlərini yox. `<target_ip>` gələcəkdə yenidən istifadə oluna bilər, `10.129.x.x` isə yox. Model uzun hash-i simvol-simvol köçürməyə çalışanda səhv edə bilər, placeholder bu riski aradan qaldırır.

### E.3. `CREATE_SYSTEM` (33-78): məsuliyyətli zənginləşdirmə

- **Vəzifəsi:** xam mətndən peşəkar ensiklopediya qeydi yazmaq. `kb`, `--merge`-in birinci addımı və `--split`-in hər qeydi bu prompt-dan istifadə edir.
- **Əsas göstərişlər:**
  - mətni sadəcə xülasə etmək olmaz, metodologiyanı və "niyə"ni saxlamaq lazımdır;
  - kurs qeydi, blog və ya ChatGPT cavabı kimi görünməməlidir;
  - mətndə olmayan, amma **dəqiq və birbaşa əlaqəli** məlumat əlavə etmək **olar**;
  - CVE, versiya və ya alət davranışı uydurmaq **olmaz**: "əmin deyilsənsə, yazma";
  - boş sözlər ("let's try", "as we can see") silinməlidir;
  - kod bloku yalnız real kod, əmr və ya HTTP üçündür;
  - sonda "Quick Reference" bölməsi olmalıdır, yalnız mənbədə olan və ya ondan birbaşa çıxan əmrlərlə. Qeyd konseptualdırsa, bu bölmə ümumiyyətlə yazılmır;
  - cavab yalnız JSON olmalıdır, `content` tək string olmalıdır.
- **Niyə belədir:** Akademiya materialı öyrənmək üçündür. Qeyd 5–10 il sonra da faydalı olmalıdır. Ona görə model mövzunu tamamlayan standart faktları əlavə edə bilər. Hallüsinasiya (uydurma) riskinə qarşı isə açıq qadağalar qoyulub.

### E.4. `MERGE_SYSTEM` (80-109)

- **Vəzifəsi:** artıq strukturlu iki qeydi (mövcud və yeni) bir qeydə birləşdirmək.
- **Əsas göstərişlər:**
  - heç bir metodologiya silinməməlidir;
  - yalnız **dəqiq** təkrarlar silinir;
  - eyni mövzulu bölmələr birləşdirilir, fərqli mövzular ayrı qalır;
  - bölmələr əsas anlayışlardan qabaqcıl texnikalara doğru düzülür;
  - nəticə "iki qeydin tikilməsi" kimi yox, tək bir səhifə kimi oxunmalıdır.
- **Niyə belədir:** merge-in ən böyük riski məlumat itkisidir. Ona görə "silmə" qaydası açıq yazılıb. Giriş hər iki tərəfdə eyni JSON formasındadır (F bölməsindəki iki addımlı dizayna baxın), bu da tapşırığı sadələşdirir.

### E.5. `CATEGORY_SYSTEM` (135-153)

- **Vəzifəsi:** başlıq və xülasəyə görə 9 kateqoriyadan birini və ya `00 Inbox`-u seçmək.
- **Əsas göstərişlər:**
  - hər kateqoriyanın yanında nümunə mövzular var;
  - qeyd konkret alət haqqındadırsa, `08 Tools` texnika kateqoriyasından üstündür;
  - əmin deyilsənsə, `00 Inbox` seç.
- **Niyə belədir:** classifier səhv edə bilər, ona görə kod onun cavabını `config.CLASSIFIER_CATEGORIES` ilə yoxlayır və şübhəli halda Inbox-a qoyur. Prompt-dakı siyahı `config` ilə eyni qalmalıdır. Bunu `test_prompt_lists_the_same_categories_as_config` testi yoxlayır.

### E.6. `SPLIT_SYSTEM` (169-200)

- **Vəzifəsi:** böyük mətni atomik qeydlərə necə bölməyi **təklif etmək**. Qeydlərin özünü yazmır.
- **Əsas göstərişlər:**
  - bir alət, bir texnika və ya bir anlayış = bir qeyd;
  - həddən artıq bölmək olmaz: kiçik detallar öz anlayışı ilə birlikdə qalır;
  - meyar "sabah X-i axtarmaq istəyəcəyəmmi?" sualıdır;
  - hər element üçün `title`, `type`, `covers`, `source_hint`.
- **Niyə belədir:** qruplaşdırma subyektiv qərardır. Ona görə model yalnız təklif verir və son qərar insanındır (README-dəki ikinci prinsip). `source_hint` sonra `process_from_plan`-da modelə mənbənin hansı hissəsinə baxmalı olduğunu göstərir.

### E.7. `WRITEUP_SYSTEM` (211-244): ciddi sədaqət

- **Vəzifəsi:** bir konkret maşının həllini sənədləşdirmək.
- **Əsas göstərişlər:**
  - bu, ensiklopediya **deyil**: ümumi nəzəriyyə əlavə etmək olmaz, mövzunu genişləndirmək olmaz (məsələn "Kerberos-un ümumiyyətlə necə işlədiyini izah etmə");
  - yalnız **bu maşında** edilənlər, edildiyi sıra ilə yazılır;
  - açıq portlar, servis versiyaları, istifadə olunan CVE kimi maşına aid faktlar saxlanılır;
  - IP, flag, token və sındırılmış şifrə kimi birdəfəlik dəyərlər placeholder olur;
  - üç bölmə: `Overview`, `Solution Walkthrough`, `Key Takeaways`. Sonuncu bu maşından çıxan və yenidən istifadə oluna bilən "tanıma nümunələri"dir.
- **Niyə belədir:** hər maşın unikaldır. Writeup-ın dəyəri onun konkretliyində və düzgün ardıcıllığındadır.

### E.8. `CREATE_SYSTEM` ilə `WRITEUP_SYSTEM` arasındakı qəsdən ziddiyyət

| | `CREATE_SYSTEM` | `WRITEUP_SYSTEM` |
|---|---|---|
| Fəlsəfə | Məsuliyyətli zənginləşdirmə | Ciddi sədaqət |
| Mənbədən kənar məlumat | Olar, əgər dəqiq və birbaşa əlaqəlidirsə | Olmaz |
| Məqsəd | Mövzunu tam öyrətmək | Bu maşının həll yolunu dəqiq qeyd etmək |
| Struktur | Mövzunun texniki quruluşu + Quick Reference | Overview / Solution Walkthrough / Key Takeaways |
| Kateqoriya | Classifier seçir | Həmişə `90 Writeups` |

README-dəki səbəb belədir: əgər writeup-lar da zənginləşdirilsəydi, hər birinə eyni ümumi nəzəriyyə əlavə olunardı. Nəticədə writeup-lar bir-birinə bənzəyər və hər maşının özünəməxsus dərsi itərdi.

---

## F. Dizayn qərarları və onların qiyməti

Hər qərar üçün üç sual cavablandırılır: nə seçildi, alternativ nə idi və bunun dürüst qiyməti nədir.

### F.1. LLM-dən əvvəl embedding axtarışı (`--merge`)

- **Seçim:** merge hədəfini tapmaq üçün əvvəl lokal embedding və cosine similarity işlədilir (`engine/memory.py:45-56`). LLM yalnız istifadəçi hədəfi seçdikdən sonra çağırılır.
- **Alternativ:** hər mövcud qeyd üçün LLM-dən "eyni mövzudurmu?" soruşmaq. Silinmiş `decide_same_topic` bunu edirdi.
- **Qiyməti:**
  - Embedding pulsuzdur, lokaldır, sürətlidir və deterministikdir. 55 qeyd üçün 55 LLM çağırışına ehtiyac yoxdur.
  - Amma o yalnız `title + summary`-ni müqayisə edir, bölmələrin məzmununu yox. Mənaca yaxın, amma fərqli sözlərlə yazılmış qeyd həddən aşağı düşə bilər.
  - Son qərarı istifadəçi verir, bu da səhv namizədin avtomatik seçilməsinin qarşısını alır.

### F.2. `CANDIDATE_THRESHOLD = 0.60`

- **Seçim:** `0.60`-dan aşağı oxşarlıq namizəd sayılmır (`engine/config.py:25`). Ən çox 5 namizəd göstərilir.
- **Dürüst qeyd:** bu rəqəm **ölçmə ilə əsaslandırılmayıb**. Hiss ilə seçilib. Repo-da merge dəqiqliyi üçün heç bir benchmark yoxdur. Bu rəqəmin doğru və ya səhv olduğunu demək üçün məlumat yoxdur.
- **Qiyməti:** hədd yüksək olsa, əsl dublikatlar görünməz və yeni qeyd yaranar. Aşağı olsa, istifadəçi alakasız namizədlər görər. İstifadəçi həmişə `0` seçib yeni qeyd yarada bilər, ona görə ikinci səhv daha ucuzdur.

### F.3. İki addımlı merge: əvvəl strukturlaşdır, sonra birləşdir

- **Seçim:** `merge_into` əvvəl yeni mətni `create_note` ilə strukturlu `Note`-a çevirir, sonra iki strukturlu qeydi `merge_two_notes`-a verir (`engine/main.py:41-43`).
- **Alternativ:** mövcud qeydi və xam mətni bir prompt-da birləşdirmək.
- **Qiyməti:**
  - Hər prompt-un bir işi var. `MERGE_SYSTEM` eyni formalı iki girişlə işləyir, bu da tapşırığı sadələşdirir.
  - Amma bu, 2 LLM çağırışı deməkdir, yəni ikiqat vaxt və xərc.
  - Birinci addımda `CREATE_SYSTEM` mətni artıq zənginləşdirə bilər, ona görə birləşən məlumat xam mətnlə tam eyni deyil.

### F.4. `MAX_RETRIES = 2`

- **Seçim:** cəmi 3 cəhd edilir (`engine/brain.py:114`). Hər retry-da səhv mesajı prompt-a əlavə olunur.
- **Qiyməti:**
  - Retry-lar çox olsa, pis prompt-da vaxt və pul itər.
  - Retry olmasa, model formatda bircə dəfə səhv edəndə bütün iş itərdi.
  - 3 cəhd hiss ilə seçilib, ölçülməyib.
  - Retry yalnız format və validation səhvləri üçündür, şəbəkə xətaları retry olunmur.

### F.5. `temperature = 0.2`

- **Seçim:** hər iki backend-də aşağı temperatur (`engine/llm.py:45`, `64`). API-də əlavə olaraq `top_p = 0.95`.
- **Qiyməti:**
  - Aşağı temperatur modelin JSON formatına və göstərişlərə daha sabit əməl etməsinə kömək edir.
  - Amma mətn daha az müxtəlif olur. Ensiklopediya üçün bu, problem deyil.
  - Sıfır yox, 0.2 seçilib. Niyə məhz 0.2 olduğu repo-da sənədləşdirilməyib.

### F.6. `_extract_json`-un `find("{")` / `rfind("}")` yanaşması

- **Seçim:** cavabdan birinci `{` ilə sonuncu `}` arasındakı hissə kəsilib `json.loads` edilir (`engine/llm.py:73-78`).
- **Niyə:** modellər bəzən JSON-dan əvvəl "Here is the note:" kimi mətn və ya ```` ```json ```` fence-i yazır. Bu yanaşma həmin "qabığı" atır.
- **Nə vaxt sınır:**
  - JSON-dan **əvvəl** və ya **sonra** gələn mətndə `{` və ya `}` olarsa, kəsilən hissəyə artıq mətn düşür;
  - model iki ayrı JSON obyekti qaytararsa;
  - cavab ortada kəsilibsə, yəni sonuncu `}` yoxdursa.

  Bütün bu hallarda `JSONDecodeError` və ya `ValueError` qalxır və retry işə düşür. JSON-un **içindəki** `{` və `}` simvolları problem yaratmır.
- **Alternativ:** API-nin "JSON mode" kimi strukturlu çıxış rejimi. Kod bundan istifadə etmir. Niyə seçilmədiyi repo-da sənədləşdirilməyib.

### F.7. `REQUEST_TIMEOUT = 2400` hər sorğu üçündür

- **Seçim:** lokal Ollama-ya göndərilən **hər bir** HTTP sorğusu 40 dəqiqəyə qədər gözləyə bilər (`engine/llm.py:49`).
- **Vacib:** bu, bütün iş üçün deyil. `--split` ilə N qeyd `1 + 2N` sorğu deməkdir və hər biri ayrıca 2400 saniyə ala bilər. Retry-lar da ayrıca sayılır.
- **Niyə belə böyükdür:** 14B model uzun kontekstdə yavaş işləyir və qısa timeout işi yarımçıq kəsərdi.
- **Digər timeout-lar:**
  - DeepSeek üçün `API_TIMEOUT = 600` saniyə, o da hər sorğu üçündür;
  - embedding üçün 60 saniyə (`engine/llm.py:30`);
  - Ollama yoxlaması üçün 5 saniyə (`engine/cli.py:19`).

### F.8. Split planının insan tərəfindən təsdiqi

- **Seçim:** model yalnız plan təklif edir. İstifadəçi elementləri birləşdirə, ata və ya bütün işi dayandıra bilər (`engine/cli.py:126-172`).
- **Alternativ:** modelin planına birbaşa əməl etmək.
- **Qiyməti:**
  - Hər `--split` interaktivdir və avtomatlaşdırılmır.
  - Amma "nə qədər atomik?" sualı subyektivdir və yanlış bölünmüş 40 qeydi sonradan düzəltmək planı əvvəlcədən düzəltməkdən qat-qat bahadır.

### F.9. Model id seçimi və alias asılılığının riski (P1-7)

- **Seçim:** `API_MODEL = "deepseek-flash"` (`engine/config.py:42`). Bu, DeepSeek-in `GET /models` siyahısındakı rəsmi addır.
- **Risk:** əvvəlki `deepseek-v4-flash` sənədləşdirilməmiş alias idi. Provayder alias-ı xəbərdarlıq etmədən silsə, API rejimi tamamilə sınar. DeepSeek adları bir dəfə artıq dəyişib (NVIDIA formatı `deepseek-ai/...` → `deepseek-v4-flash` → `deepseek-flash`). `/models`-i vaxtaşırı yoxlamaq faydalıdır.

### F.10. Yazma sırası: embedding → fayl → index (P1-4)

- **Seçim:** `main.save_note` (`engine/main.py:4-9`).
- **Niyə:** uğursuzluq ehtimalı ən yüksək olan addım şəbəkədir, ona görə o birinci gəlir. O uğursuz olsa, heç nə yazılmır.
- **Rədd edilən iki variant:**
  - Əvvəl index, sonra fayl: fayl yazısı uğursuz olsa, ghost yazı qalardı.
  - Uğursuzluqda faylı silmək (rollback): merge zamanı fayl köhnəsinin üzərinə yazılır, ona görə silinən fayl orijinal qeydin özü ola bilərdi.
- **Qalan risk:** fayl yazılır, amma index yazısı uğursuz olur. Bu halda fayl index-də olmur. İki disk əməliyyatı yan-yana olduğu üçün bu ehtimal azdır, `kb --reindex` isə bu halı tapıb düzəldir.

### F.11. Bir kateqoriya siyahısı, iki ad (P1-2)

- **Seçim:** `CLASSIFIER_CATEGORIES` (10) və `VAULT_CATEGORIES` (13), hər ikisi `config.py`-də. Qovluq skanı açıq siyahıya əsaslanır, `NN ` prefiksi regex-inə yox.
- **Qiyməti:** Obsidian-da yaradılan yeni qovluq `config.py`-yə əlavə olunana qədər CLI üçün görünməzdir (H bölməsi).

### F.12. Server yalnız localhost-da (P2-6)

- **Seçim:** `SERVER_HOST = "127.0.0.1"`. Public rejim tokenlə işləyə bilər, amma qurulmayıb.
- **Qiyməti:** M1-dən şəbəkə ilə göndərmə hazırda işləmir. Bu yol onsuz da real istifadədə deyil (I bölməsi).

---

## G. Xəta halları

| Simptom | Səbəb | Harada qalxır | Həlli |
|---|---|---|---|
| `ERROR: Ollama is not reachable at ..., or the embedding model 'nomic-embed-text' is not pulled` | Ollama işləmir və ya model yüklənməyib | `engine/cli.py:28-32` (`require_ollama`) | Ollama-nı işə salın, `ollama pull nomic-embed-text` |
| Server-də 500: `ConnectionError ... /api/embeddings` | Server Ollama-nı əvvəlcədən yoxlamır | `engine/llm.py:27-32` (`embed`), `engine/main.py:7` | Ollama-nı işə salın. Fayl yazılmayıb |
| `--local`-da HTTP 404 və ya model xətası | `qwen3:14b` yüklənməyib (CLI bunu yoxlamır) | `engine/llm.py:37-51` (`_ask_json_local`) | `ollama pull qwen3:14b` |
| `ERROR: DEEPSEEK_API_KEY not found. Check your .env file.` | `.env` yoxdur və ya açar boşdur | `engine/llm.py:18-20` | `~/cke/.env`-ə `DEEPSEEK_API_KEY=...` yazın |
| `ERROR: ...` (openai auth xətası, 401) | API açarı səhvdir və ya vaxtı keçib | `engine/llm.py:58` (`client.chat.completions.create`) | Açarı yeniləyin. Retry olunmur |
| `ERROR: ...` (model tapılmadı) | DeepSeek model adını dəyişib və ya silib | `engine/llm.py:58` | `GET /models`-ə baxın, `config.API_MODEL`-i yeniləyin (F.9) |
| `Attempt N rejected: ... JSON ...` | Model cavabında JSON yoxdur və ya JSON pozulub | `engine/llm.py:76-78` (`_extract_json`) | Avtomatik retry olunur |
| `Attempt N rejected: ... validation error ...` | JSON var, amma forması səhvdir: boş başlıq, `content` `None`-dur və s. | `engine/brain.py:120` → `engine/schema.py` | Avtomatik retry olunur, səhv mesajı prompt-a əlavə edilir |
| `ERROR: Model failed to produce valid output after 3 attempts. Last error: ...` | Üç cəhdin üçü də uğursuz olub | `engine/brain.py:124` | Mətni qısaldın və ya sadələşdirin, `--local` ilə sınayın. Heç nə yazılmayıb |
| `ERROR during planning: ...` | `--split` planı 3 cəhddən sonra da yararsızdır | `engine/cli.py:116-119` | Yenidən işə salın və ya mətni bölün. Heç nə yazılmayıb |
| `ERROR: Note '<slug>' not found` (merge) | Index-də ghost yazı var: fayl silinib və ya köçürülüb | `engine/main.py:35-36` | `kb --reindex` |
| `ERROR: Note '<slug>' exists in more than one category (...)` | Eyni slug iki qovluqdadır | `engine/vault.py:36-39` (`find_note`) | Bir faylı əl ilə silin, sonra `kb --reindex` |
| `ERROR: Merged title '...' gives an empty filename. Nothing was changed.` | Model yararsız başlıq qaytarıb | `engine/main.py:47-48` | Merge-i yenidən işə salın. Vault dəyişməyib |
| `Title changed to '...'; keeping the filename ...` (və ya `..., but <kateqoriya>/<slug>.md is another note; keeping the filename ...`) | Merge başlığı dəyişib, amma rename təsdiqlənməyib, və ya yeni ad başqa qeydə aiddir | `engine/main.py:52-60` | Xəta deyil, qəsdən belədir |
| `STOPPED: a note with this filename already exists. Nothing was written.` (`kb`), `skipped (already exists): ...` (`--split`), `ERROR: Note '<slug>' already exists in ...` (`--writeup`; server-də 500) | Bu slug-lı qeyd vault-da artıq var. Yaradılış mövcud qeydi heç vaxt əvəz etmir (P0-3) | `engine/vault.py:52-56` (`ensure_new`), `59-70` (`write_note`) | Mətni mövcud qeydə əlavə etmək üçün `kb --merge`. `--split`-də elementi `drop` etmək olar |
| `Input too short (N chars). Nothing saved.` | `kb`/`--merge` üçün 30-dan, `--split`/`--writeup` üçün 100-dən az simvol | `engine/cli.py:323-325`, `104-106`, `298-300` | Daha uzun mətn verin |
| `File not found: <path>` | `--file` yolu səhvdir | `engine/cli.py:61-63` | Yolu yoxlayın |
| `kb --reindex` hesabatında `remove from index` / `fix category` / `add to index` | Index və vault uyğunsuzdur (Finder/Obsidian-da silmə və ya köçürmə) | `engine/main.py:93-110` | `yes` cavabı verin |
| `kb --reindex`-də `WARNING ... nested` / `missing at the top level` | Kateqoriya qovluğu yanlış yerdədir | `engine/vault.py:9-18` | Qovluğu əl ilə düzəldin |
| Server `401 {"error": "unauthorized"}` | Public rejimdə token yoxdur və ya səhvdir | `engine/server.py:30-31` | `Authorization: Bearer <CKE_SERVER_TOKEN>` göndərin |
| `server.log`-da `Address already in use` | Port 8000 məşğuldur, məsələn server əl ilə ikinci dəfə işə salınıb | Flask/werkzeug, `engine/server.py:59` | Əl ilə işə salmayın. launchd agent-i kifayətdir |
| Index-də JSON xətası (`load_index`) | `.kb_index.json` korlanıb: yarımçıq yazı və ya Syncthing konflikti | `engine/memory.py:7` | Backup-dan bərpa edin (`~/Desktop/kb_index-prefix.json`) və ya faylı silib `kb --reindex` ilə yenidən qurun |

---

## H. Sistemi genişləndirmək

Bu bölmə modulluq iddiasını yoxlayır: harada asandır və harada kod bir-birinə bağlıdır.

### H.1. Yeni kateqoriya

1. `engine/config.py:10-13`-də `CLASSIFIER_CATEGORIES`-ə əlavə edin (classifier seçə bilsin deyə). Ya da yalnız `VAULT_CATEGORIES`-ə əlavə edin (`engine/config.py:16`): onda qovluq görünəcək, amma classifier onu seçməyəcək.
2. Classifier üçünsə, `CATEGORY_SYSTEM` prompt-una (`engine/brain.py:138-147`) eyni formatda bir sətir əlavə edin: `- 10 Crypto        (...)`. Bunu unutsanız, `test_prompt_lists_the_same_categories_as_config` testi sınacaq.
3. Vault-da qovluğu yaradın və ya ilk qeydin onu yaratmasını gözləyin. `kb --reindex` çatışmayan qovluğu xəbərdarlıq kimi göstərir.

**Qiymətləndirmə:** asandır, amma iki yerə toxunmaq lazımdır: `config` və prompt. Test onları uyğun saxlayır.

### H.2. Başqa chat modeli

- **Lokal:** `config.CHAT_MODEL`-i dəyişin, sonra `ollama pull <model>`.
- **OpenAI ilə uyğun API:** `config.API_BASE_URL` və `config.API_MODEL`-i dəyişin. `.env`-dəki açar adı (`DEEPSEEK_API_KEY`) `engine/llm.py:18`-də birbaşa yazılıb, onu da dəyişmək lazım ola bilər.
- **OpenAI ilə uyğun olmayan provayder:** `engine/llm.py`-də yeni `_ask_json_<ad>` funksiyası yazın və `ask_json`-a (`engine/llm.py:81-86`) yeni qol əlavə edin. `cli.py`-də backend-i seçən flag lazım olacaq.

**Qiymətləndirmə:** yaxşı ayrılıb. `brain.py` və `main.py` modeli tanımır, yalnız `ask_json`-u çağırır.

### H.3. Başqa embedding modeli

1. `config.EMBED_MODEL`-i dəyişin və modeli `ollama pull` ilə yükləyin. `check_ollama` yeni modeli avtomatik yoxlayacaq.
2. **Vacib:** köhnə vektorlar yeni vektorlarla müqayisə oluna bilməz. Ölçü də fərqli ola bilər. Index yenidən qurulmalıdır: `.kb_index.json`-u ehtiyat nüsxəyə köçürün, sonra `kb --reindex` bütün qeydləri "add to index" kimi görəcək və hamısını yenidən embed edəcək.
3. `CANDIDATE_THRESHOLD` (0.60) yeni model üçün mənasını itirə bilər, çünki oxşarlıq paylanması modeldən asılıdır.

**Qiymətləndirmə:** kodda bir sətirlik dəyişiklikdir, amma məlumat miqrasiyası tələb edir. Index-də vektorun hansı modeldən gəldiyi saxlanmır, ona görə qarışıq index-i kod özü aşkar etmir.

### H.4. Yeni CLI rejimi

1. `engine/cli.py`-də `run()`-a flag qolu əlavə edin. Rejim embedding tələb edirsə, qol `require_ollama()`-dan (`engine/cli.py:277`) sonra olmalıdır, tələb etmirsə, `--delete` kimi ondan əvvəl.
2. İnteraktiv hissəni `handle_<ad>()` funksiyasına, iş axınını isə `engine/main.py`-yə yazın. Yazma lazımdırsa, `save_note`-dan istifadə edin ki, sıra qorunsun.
3. Yeni prompt lazımdırsa, `engine/brain.py`-də onu və `generate_validated`-i çağıran funksiyanı əlavə edin. Yeni cavab forması lazımdırsa, `engine/schema.py`-də model yazın və onu `schema=` ilə ötürün (`--split` kimi).
4. `tests/test_cke.py`-yə `VaultTestCase` əsasında test əlavə edin.

**Qiymətləndirmə:** nümunə hazırdır (`--writeup` ən sadəsidir). `run()` uzun bir funksiyadır (`engine/cli.py:268-389`), ona görə flag-ların sırası diqqət tələb edir.

### H.5. Başqa saxlama formatı

Ən çox bağlılıq buradadır:

- `vault.to_markdown` / `markdown_to_json` formatın özüdür. Onları dəyişmək kifayət deyil.
- `main.repair_index` faylın yolunu özü qurur (`engine/main.py:118`, `config.VAULT / category / f"{slug}.md"`). Bu, saxlama detalının `main.py`-yə sızmasıdır.
- `list_all_notes` `*.md` uzantısına bağlıdır (`engine/main.py:76`).
- Slug həm fayl adı, həm də index açarıdır. Saxlama formatı dəyişsə, açar sxemi də yenidən düşünülməlidir.
- `server.add_note` kateqoriyanı `vault.find_note` ilə tapır.

**Qiymətləndirmə:** modulluq qismən var. Fayl əməliyyatlarının çoxu `vault.py`-dədir, amma `main.py` bir-iki yerdə yol və uzantı haqqında bilir. Markdown-dan imtina etmək bir neçə modula toxunmağı tələb edər.

---

## I. Məlum məhdudiyyətlər və gələcək iş

### Məhdudiyyətlər

1. **Merge dəqiqliyi ölçülməyib.** `CANDIDATE_THRESHOLD = 0.60` hiss ilə seçilib. Benchmark yoxdur.
2. **Avtomatik məna yoxlaması yoxdur.** "Bir mövzu = bir qeyd" qaydası insanın seçiminə və slug unikallığına əsaslanır (A bölməsi).
3. **Server `--split` və `--writeup` edə bilmir.** Yalnız `process`-i import edir (`engine/server.py:5`).
4. **Server Ollama-nı əvvəlcədən yoxlamır.** Ollama sönülü olanda DeepSeek xərci itir, fayl isə yazılmır.
5. **Index sinxronlaşdırılan qovluqdadır.** `.kb_index.json` Syncthing ilə sinxronlaşır. Pipeline iki maşında eyni vaxtda işləsə, konflikt yarana bilər.
6. **Index atomik yazılmır** (`engine/memory.py:12`). Yazma yarıda kəsilsə, fayl korlana bilər.
7. **Prompt injection qarşısı alınmayıb.** Etibarsız mətn birbaşa LLM-ə gedir və modelin nəticəsi diskə yazılır. Məsələn, kopyalanan materialın içində "əvvəlki göstərişləri unut və ..." kimi gizli təlimat ola bilər. Hazırkı müdafiə yalnız bunlardır:
   - schema yalnız gözlənilən JSON formasını qəbul edir;
   - kateqoriya siyahıdan kənara çıxa bilmir;
   - slug yol keçidinə (path traversal) imkan vermir;
   - server defolt olaraq yalnız localhost-da dinləyir.

   Qeydin **məzmununu** heç nə yoxlamır.
8. **`--local` chat modelinin varlığını yoxlamır.** Yalnız embedding modeli yoxlanır.
9. **Fence qaydası sadələşdirilib** (C.3), çox sətirli preambula isə bir sətrə birləşir.
10. **Qeyri-latın başlıqlar** slug-da hərflərini itirir (`"Café"` → `"caf"`). Heç bir latın hərfi qalmırsa, `untitled-<hash>` alınır.
11. **Bəzi timeout-lar config-də deyil** (C.1).

### Gələcək iş

1. **M1 client üçün server-in yenidən yazılması.** M1 tərəfi real istifadəyə veriləndə server bütün pipeline-ı (`--split`, `--writeup`, `--merge`) dəstəkləməli olacaq. Onda bunlar da edilməlidir:
   - `SERVER_HOST`-u şəbəkəyə açmaq və `.env`-də `CKE_SERVER_TOKEN` qurmaq. Token yoxlaması kodda artıq var və testlənib (`engine/server.py:14-20`), amma hazırda qurulmayıb;
   - Ollama-nı əvvəlcədən yoxlamaq;
   - log rotation-u launchd və ya `newsyslog` vasitəsilə həll etmək.

   Bu, Nazirin 2026-10-12 qərarıdır: hələlik localhost (variant a), token yolu isə server yenidən yazılanda.
2. **Böyük girişlər üçün chunking.** `--split` mətni modelə bütöv göndərir, onu kontekstə sığdıracaq mexanizm isə yoxdur. Giriş və çıxış birlikdə 128K tokenlik kontekstə sığmalıdır. Çıxışa `max_tokens=32768` ayrılıb (`engine/llm.py:66`), ona görə system prompt-dan sonra girişə təxminən 95K token qalır.
   - Adi ingilis mətnində (~1.3 token/söz) bu, təxminən **70K söz** edir. Əmrlər, hash-lər və IP-lər token sayını artırır. Köhnə modulun öz ehtiyatlı təxmini ilə (1.8 token/söz) hədd ~50K sözdür. 100K sözlük giriş üçün chunking hər halda lazımdır.
   - `--local`-da hədd xeyli aşağıdır: `NUM_CTX = 8192` token (`engine/config.py:27`).
   - 128K rəqəminin özü yoxlanmayıb (`Solution.md` → "Hələ açıq").

   Köhnə modul `65d8b47^`-də qalır (`git show 65d8b47^:engine/chunker.py`), amma olduğu kimi qaytarılmamalıdır: `####` başlıqlarını tanımırdı və kod blokundakı `# ` sətrini başlıq sayırdı. Onu yenidən yazmaq lazımdır. Təməl P0-1-in fence-aware parseri olmalıdır (`engine/vault.py:107-139`).
3. **`--split` hər qeyd üçün bütün mətni yenidən göndərir.** `process_from_plan` hər plan elementi üçün `focus_prompt`-a **tam** mənbə mətni qoyur (`engine/main.py:150-158`). 50 qeydlik planda eyni modul 50 dəfə göndərilir, API xərci və vaxt da təxminən o qədər artır. Bu problem chunking-dən asılı deyil və kiçik modullarda da indi xərc yaradır.
   - Kontekst limiti hər çağırışa ayrıca tətbiq olunur. Qeydlərin sayı limiti özü aşmır, amma mətn bir çağırışa sığmırsa, 50 çağırışın heç biri sığmır.
   - **Həll:** hər qeydə yalnız öz hissəsini göndərmək. Plan hər element üçün artıq `source_hint` qaytarır ("which heading(s) or part(s) of the input this note draws from", `engine/brain.py:195`). Hazırda bu sahə mətni kəsmək üçün istifadə olunmur, prompt-a yalnız göstəriş kimi gedir. Chunking-in parseri ilə birlikdə hissəni məhz bu sahəyə görə seçmək olar.
4. Index üçün atomik yazma: müvəqqəti fayl, sonra `os.replace`.
5. `CANDIDATE_THRESHOLD` üçün kiçik, əl ilə etiketlənmiş benchmark.
6. Prompt injection üçün ən azı bunlar: girişin sərhədlərini açıq qeyd etmək və nəticəni məzmun baxımından yoxlamaq.

Təmir tapşırığındakı P2 bəndlərinin hamısı bağlanıb. P2-6-da kod hazırdır, token qurulması isə yuxarıdakı səbəblə təxirə salınıb.

---

## J. Lüğət

| Termin | İzah |
|---|---|
| **atomic note** (atomik qeyd) | Yalnız bir aləti, bir texnikanı və ya bir anlayışı əhatə edən qeyd. Sabah ayrıca axtarılacaq hər mövzu öz qeydini alır |
| **backend** | Chat modelinin işlədiyi yer: `api` (DeepSeek bulud xidməti) və ya `local` (kompüterdəki Ollama). Embedding həmişə lokaldır |
| **callback** | Bir funksiyaya ötürülən və sonra onun tərəfindən çağırılan başqa funksiya. `merge_into` rename sualını `confirm_rename` callback-i vasitəsilə verir |
| **chunk** (hissə) | Böyük mətnin kiçik parçası. Silinmiş `chunker.py` mətni başlıqlara görə chunk-lara bölürdü. Hazırkı kodda chunk yoxdur: `--split` mətni bütöv göndərir |
| **cosine similarity** (kosinus oxşarlığı) | İki vektorun istiqamətinin nə qədər yaxın olduğunu ölçür. 1 eyni istiqamət deməkdir, 0 əlaqə yoxdur deməkdir. `memory.similarity` bunu hesablayır |
| **embedding** | Mətnin mənasını əks etdirən rəqəm vektoru. Mənaca yaxın mətnlərin vektorları da yaxın olur. Burada `nomic-embed-text` hər mətn üçün 768 rəqəm qaytarır |
| **fence** (kod bloku sərhədi) | Markdown-da kod blokunu açan və bağlayan ```` ``` ```` və ya `~~~` sətri |
| **hash** (heş) | Mətndən hesablanan qısa "barmaq izi". Eyni mətn həmişə eyni heşi verir. `slugify` boş nəticədə SHA-256 heşinin ilk 8 simvolundan istifadə edir |
| **index** | `.kb_index.json`: hər qeydin slug-u, embedding-i, başlığı və kateqoriyası. Oxşar qeyd axtarışı bunun üzərində işləyir |
| **LLM** (böyük dil modeli) | Mətn yaradan model. Burada DeepSeek və ya Qwen |
| **placeholder** (yer tutucu) | Konkret, birdəfəlik dəyərin yerinə yazılan ümumi işarə, məsələn `<target_ip>`, `<hash>` |
| **prompt injection** | Modelə verilən mətnin içinə gizlədilmiş və modeli əsl göstərişlərə qarşı yönləndirən təlimat |
| **retry** (təkrar cəhd) | Model səhv formatda cavab verəndə səhv mesajı ilə yenidən soruşmaq. Burada ən çox 2 dəfə |
| **round-trip** (gediş-dönüş) | Faylı oxuyub obyektə çevirmək, sonra yenidən fayla yazmaq. Lossless round-trip heç bir məlumatın itməməsi deməkdir |
| **schema validation** (sxem yoxlaması) | Məlumatın gözlənilən formaya uyğun olub-olmadığını yoxlamaq. Burada Pydantic modelləri ilə edilir (`engine/schema.py`) |
| **slug** | Başlıqdan düzəldilən, fayl adı kimi istifadə olunan qısa ad. Məsələn "Nmap Port Scanning" → `nmap-port-scanning`. Həm fayl adıdır, həm də index açarı |
| **TTY** | İnteraktiv terminal. `stdin` TTY deyilsə (məsələn pipe və ya server), istifadəçidən sual soruşmaq mümkün deyil |
| **vault** | Obsidian-ın qeydlər qovluğu, burada `~/Documents/CyberKB` |
| **LaunchAgent** | macOS-da istifadəçi daxil olanda proqramı avtomatik işə salan və (`KeepAlive` ilə) dayananda yenidən başladan konfiqurasiya. `com.cke.server` server-i belə işə salır |
