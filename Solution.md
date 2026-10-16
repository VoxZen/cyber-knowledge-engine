# CKE: təmir hesabatı (Solution.md)

**Repo:** `VoxZen/cyber-knowledge-engine`, lokal yolu `~/cke`
**Vault:** `~/Documents/CyberKB`
**Tarix:** 2026-10-12 – 2026-10-13
**Başlanğıc nöqtəsi:** `4deedd0` (iş ağacı təmiz idi, `main` == `origin/main`)
**Son vəziyyət:** 21 kod, test və sənəd commit-i (2026-10-13-də əlavə edilən P0-3 daxil), üstəgəl bu sənədin və `Explanation.md`-nin öz commit-ləri. Heç biri push edilməyib.

Bu sənəd hər bənd üçün dörd suala cavab verir: nə dəyişdi, niyə məhz belə dəyişdi, necə yoxlanıldı və hansı commit-dədir. Sətir nömrələri **hazırkı HEAD**-ə görədir. Terminal çıxışları real işlədilmiş əmrlərdən götürülüb. Bəzi əmrlərin sonunda `grep`/`sed` filtri var, ona görə çıxış həmin filtrlənmiş əmrin dəqiq nəticəsidir.

İlk dəfə işlənən ingilis terminlərinin yanında mötərizədə qısa izah var. Tam lüğət `Explanation.md`-nin J bölməsindədir.

---

## İşin ardıcıllığı

1. Xarici yoxlamalar: Ollama modelləri və DeepSeek model id-si (§0.3).
2. Vault və index-in backup-ı, sonra backup-ın yoxlanması.
3. P2-5 (`CKE_VAULT`): test dəsti real vault-a toxunmasın deyə ən əvvəl edildi.
4. `tests/test_cke.py`. Hər test əvvəl **düzgün səbəbdən** uğursuz oldu, sonra düzəlişə keçildi.
5. P0 → P1 (P1-2, P1-1-dən əvvəl) → P2 → P3.
6. Vault-u dəyişən hər addımdan əvvəl Nazirin təsdiqi alındı.
7. 2026-10-13: Nazirin qərarı ilə P0-3 (əvvəl "Hələ açıq" siyahısında 1-ci bənd idi).

---

## P0-1 · `markdown_to_json` başlığı korlayırdı, `--merge` isə qeydi silirdi

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** Parser faylı sətir-sətir oxuyurdu və `# ` ilə başlayan **hər** sətri başlıq sayırdı. Kod bloklarını izləmirdi, ona görə ```` ```bash ```` blokunun içindəki shell şərhi (`# scan all ports`) də başlıq sayılırdı. Fayldakı **sonuncu** belə sətir qalib gəlirdi. Həmin sətir heç bir bölməyə də yazılmırdı, yəni itirdi.

`merge_into` yeni fayl adını, yəni slug-u (başlıqdan düzəldilən fayl adı), bu korlanmış başlıqdan çıxarırdı. Slug dəyişəndə **əvvəlcə köhnə faylı silirdi**, yenisini sonra yazırdı. Nəticədə növbəti `kb --merge` `nmap.md`-ni silib əvəzinə `skip-host-discovery-when-the-target-does-not.md` adlı fayl yazacaqdı.

Köhnə parser-i git tarixçəsindən (`4deedd0`) götürüb real vault-da öz ölçməmi apardım. Nəticə audit ilə eynidir:

```
OLD parser (4deedd0): title correct 25, corrupted 30, code lines dropped 143
NEW parser (HEAD):    title correct 55, corrupted 0
```

**Dəyişiklik.**

1. `engine/vault.py:107-139` (`markdown_to_json`): fence (kod blokunu açan və bağlayan ```` ``` ```` və ya `~~~` sətri) izlənir. Başlığı yalnız birinci `# ` sətri təyin edir.

````diff
     for line in lines:
-        if line.startswith("# "):
-            data["title"] = line[2:].strip()
+        marker = line.lstrip()[:3]
+        if fence:
+            # Inside a code block every line is content; only the same marker closes it
+            if marker == fence:
+                fence = None
+        elif marker in ("```", "~~~"):
+            fence = marker
+        elif line.startswith("# ") and not data["title"]:
+            # Only the first level-1 heading is the title; a later "# " is content
+            data["title"] = line[2:].strip()
+            continue
         elif line.startswith("## "):
````

2. `engine/main.py:33-71` (`merge_into`): əvvəl yazılır, sonra silinir. Boş slug olarsa merge dayanır. Rename yalnız istifadəçinin təsdiqi ilə olur.

```diff
-def merge_into(text, target_slug, backend=None):
+def merge_into(text, target_slug, backend=None, confirm_rename=None):
 ...
-    new_slug = vault.slugify(merged.title)
-    if target_slug != new_slug:
-        vault.delete_note(target_slug)
-        memory.remove_entry(target_slug)
-    vault.write_note(new_slug, category, vault.to_markdown(merged))
-    memory.update_entry(new_slug, merged.title, merged.summary, category)
+    new_slug = vault.slugify(merged.title, fallback=False)
+    if not new_slug:
+        raise RuntimeError(f"Merged title '{merged.title}' gives an empty filename. Nothing was changed.")
+    if new_slug != target_slug and not (confirm_rename and confirm_rename(target_slug, new_slug)):
+        print(f"Title changed to '{merged.title}'; keeping the filename {target_slug}.md")
+        new_slug = target_slug
+    ...
+    save_note(new_slug, category, merged)
+    if new_slug != target_slug:
+        vault.delete_note(target_slug)
+        memory.remove_entry(target_slug)
```

`save_note` P1-4-də, `fallback=False` isə P1-6-da əlavə olundu. Yuxarıdakı kod son haldır.

3. `engine/cli.py:35-41` (`confirm_rename`) və `engine/cli.py:395-400` (`ask_rename`): sual CLI-da verilir. Terminal yoxdursa (`stdin` TTY deyil), cavab avtomatik "yox" sayılır. Sual çıxmazdan əvvəl spinner dayandırılır, yoxsa onun üstünə yazardı.

**Niyə bu yanaşma.**

- **Fence izləmə üçün bir dəyişən kifayətdir.** `fence` ya `None`-dur, ya da açan marker-dir. Blok yalnız **eyni** marker ilə bağlanır, ona görə ```` ``` ```` blokunun içindəki `~~~` sətri onu bağlamır. Bunu `nested_fence.md` fixture-i yoxlayır.
  - Rədd etdim: Markdown kitabxanası, çünki yeni dependency qadağandır.
  - Rədd etdim: bütün sənədə tətbiq olunan regex, çünki izahı çətindir.
- **Girintiyə dözümlülük yoxdur.** `dns-record-types.md`-nin birinci sətrində başlıqdan əvvəl artıq bir tab var idi (`\t# ...`). CommonMark qaydasına görə belə sətir başlıq deyil, kod blokudur. Nazir parser-i dözümlü etməyi rədd etdi (B variantı). Bunun əvəzinə vault-dakı tab silindi (A variantı, aşağıdakı vault cədvəlinə baxın).
- **Merge-də sual yalnız `cli.py`-də verilir.** `main.py` işi görür, `cli.py` isə istifadəçi ilə danışır. `confirm_rename` callback-dir (çağırana ötürülən funksiya). Ötürülməyəndə, məsələn server-də, təhlükəsiz davranış seçilir: fayl adı dəyişmir, başlığın dəyişdiyi isə çap olunur.
  - Rədd etdim: `merge_into`-nun özünün `input()` çağırması. Bu, server-i və testləri dondurardı.
  - Rədd etdim: boş slug üçün avtomatik ad yaratmaq. Tapşırıq bunu qadağan edir, həm də bu, modelin səhvini gizlədərdi.
- **Miqrasiya edilmədi.** Diskdəki 55 qeyd düzgün idi, səhv yalnız parser-də idi. Heç bir qeydin başlığı və ya adı dəyişdirilmədi.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P0_1 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_cli_never_confirms_without_a_terminal ... ok
test_confirmed_rename_writes_new_note_before_deleting_old ... ok
test_crash_while_indexing_keeps_the_original_note ... ok
test_declined_rename_keeps_filename ... ok
test_title_change_without_confirmation_keeps_filename ... ok
test_unusable_title_aborts_and_leaves_vault_untouched ... ok
test_fence_closes_only_with_its_own_marker ... ok
test_only_the_first_h1_is_the_title ... ok
test_round_trip_keeps_title_headings_and_code ... ok
test_shell_comment_in_code_block_is_not_the_title ... ok
test_tilde_fence_hides_headings ... ok
test_every_real_note_round_trips ... skipped 'set CKE_VAULT to the real vault to run this read-only check'
Ran 12 tests in 0.007s
OK (skipped=1)
```

Real vault-dakı bütün qeydlər yerində oxundu, heç nə köçürülmədi və yazılmadı:

```
$ CKE_VAULT=~/Documents/CyberKB python -m unittest discover -s tests -v -k every_real_note
test_every_real_note_round_trips (test_cke.P0_1_RealVaultRoundTrip.test_every_real_note_round_trips) ...
real vault round trip: 55/55 notes keep title, headings and every code line
ok

----------------------------------------------------------------------
Ran 1 test in 0.005s

OK
```

Düzəlişdən əvvəl bu test `24/55` göstərirdi: 30 qeyddə başlıq korlanırdı, 1 qeyddə (`dns-record-types.md`) isə tab səbəbindən sütun 0-da başlıq yox idi.

**Commit:**
- `2732854 test: add baseline unittest suite for P0/P1 items`
- `095866e fix(P0-1): preserve note title when parsing markdown, make merge safe`

---

## P0-2 · Fərqli kateqoriyalardakı eyni slug faylları sahibsiz qoyurdu

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `write_note` nəyə baxmadan verilən kateqoriyaya yazırdı və eyni slug-un başqa qovluqda olub-olmadığını yoxlamırdı. Index (`.kb_index.json`, hər qeydin embedding-i, yəni mətnin rəqəmsal vektoru) yalnız slug ilə açarlanır. Ona görə ikinci yazı birinci index yazısını əvəz edirdi. `find_note` isə `iterdir()`-in ilk qaytardığı nüsxəni seçirdi, `iterdir()` isə heç bir ardıcıllıq vəd etmir. Nəticədə bir fayl diskdə qalırdı, amma index-də yox idi.

**Dəyişiklik.**

- `engine/vault.py:30-42` (`find_note`): bütün uyğun faylları toplayır. Birdən çox tapılarsa, kateqoriyaları sadalayan `RuntimeError` qaldırır. Qovluqlar sabit ardıcıllıqla gəzilir: əvvəl `sorted(...)` ilə, P1-2-dən sonra `config` sırası ilə.
- `engine/vault.py:59-70` (`write_note`): əvvəl yeni fayl yazılır, sonra köhnə kateqoriyadakı fayl silinir. P0-3-dən sonra bu, yalnız `replace=True` ilə, yəni merge-də baş verir.
- `engine/cli.py:254-259`: dublikat xətası `kb --delete`-də traceback kimi yox, `ERROR: ...` kimi göstərilir.

```diff
 def write_note(slug, category, markdown):
+    old_path, old_category = find_note(slug)
     category_path = config.VAULT / category
     category_path.mkdir(parents=True, exist_ok=True)
     (category_path / f"{slug}.md").write_text(markdown, encoding="utf-8")
+    # One slug, one file: if the note was in another category, it has now moved here
+    if old_category is not None and old_category != category:
+        old_path.unlink()
```

**Niyə bu yanaşma.** Burada iki ağlabatan dizayn var idi:

- **"Rədd et":** eyni slug başqa kateqoriyadadırsa, yazma. Sadədir. Amma adi `kb` hər dəfə `choose_category`-ni yenidən çağırır və model eyni mövzunu sonrakı dəfə başqa qovluğa qoya bilər. Bu halda adi qeyd yaratma sınardı.
- **"Köçür, sonra yaz"** (seçdim): bir slug həmişə bir faylda qalır. Faylın yeri son təsnifata görə dəyişir. Əvvəlcə yeni fayl yazılır, köhnəsi yalnız ondan sonra silinir. Bu, P0-1-dəki "əvvəl yaz, sonra sil" prinsipi ilə eynidir: proses yarıda qırılsa, iki nüsxə qalar, amma heç biri itməz.

Bu seçimin qiyməti var. Qeyd səssizcə başqa qovluğa keçə bilər, istifadəçi bunu yalnız `create: 08 Tools/nmap.md` sətrindən görür. Bundan başqa, adi `kb` mövcud qeydin məzmununu onsuz da yenisi ilə əvəz edirdi. Bu, köhnə davranış idi və P0-3-də düzəldildi: yeni qeyd artıq heç bir kateqoriyada mövcud slug-a yazılmır, ona görə yuxarıdakı "səssiz köçmə" də yalnız merge-ə aiddir.

`find_note`-un dublikat görəndə xəta verməsi bilərəkdəndir: silmə, oxuma və merge səhv nüsxəni təxmin etmək əvəzinə dayanır. P1-1-dəki `kb --reindex` isə `find_note`-dan istifadə etmir, ona görə dublikat olanda da işləyir və onu göstərir.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P0_2 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_delete_refuses_an_ambiguous_slug ... ok
test_find_note_reports_a_slug_in_two_categories ... ok
test_reclassified_topic_leaves_no_orphan ... ok
test_writing_into_a_new_category_moves_the_note ... ok
Ran 4 tests in 0.005s
OK
```

Sintetik vault-da real CLI ilə yoxlama apardım. Hər iki fayl yerində qaldı:

```
$ printf '1\nyes\n' | CKE_VAULT=<sintetik vault, scratchpad-da> python -m engine.cli --delete
All notes:
  1. nmap  (01 Networking)
  2. nmap  (08 Tools)
  0. Cancel

Delete which note? (0-2): Delete 'nmap'? This cannot be undone. (yes/no): ERROR: Note 'nmap' exists in more than one category (01 Networking, 08 Tools). Keep one file and remove the others.
```

Real vault-da bu gün dublikat slug yoxdur (`duplicate slugs: 0`).

**Commit:** `1c84850 fix(P0-2): keep one file per slug across categories`

---

## P0-3 · Yeni qeyd eyni adlı mövcud qeydin üzərinə yazırdı

Bu bənd audit-də yox idi. Təmir zamanı tapıldı və "Hələ açıq" siyahısında 1-ci bənd idi. 2026-10-13-də Nazir onu P0-3 kimi açdı və iki yol üçün fərqli davranış təyin etdi.

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `vault.write_note` slug-ın artıq mövcud olub-olmadığına baxmadan yazırdı:

- eyni kateqoriyada `write_text` faylın üzərinə yazırdı və köhnə qeydin bütün məzmunu itirdi;
- başqa kateqoriyada P0-2-nin "köçür" qaydası işləyirdi: yeni fayl yazılır, köhnəsi silinirdi. Nəticə eyni idi, köhnə məzmun itirdi.

Bu yola dörd giriş çatırdı: adi `kb` (`process`), `kb --split` (`process_from_plan`), `kb --writeup` (`process_writeup`) və server (`process`). Bundan başqa, merge-də rename təsdiqlənəndə yeni ad **başqa** bir qeydə aid ola bilərdi və o qeyd də əvəz olunurdu. Köhnə kodun sintetik vault-dakı nəticəsi (HEAD `0eda6b4`, model mock edilib):

```
before: 08 Tools/dig.md -> Original summary.
before: 90 Writeups/box-one.md -> First attempt.
kb, same category: 08 Tools/dig.md -> New summary.
kb, other category: 08 Tools/dig.md -> MISSING
kb, other category: 01 Networking/dig.md -> New summary.
--writeup: 90 Writeups/box-one.md -> New summary.
```

**Nazirin qərarı.** İki yol fərqli davranmalıdır:

- **`kb` (tək qeyd):** slug varsa dayansın, mövcud qeydin adını və kateqoriyasını göstərsin, `kb --merge` təklif etsin və heç nə yazmasın.
- **`kb --split`:** dayanmaq 40-50 qeydlik planı yarıda qoyardı. Ona görə planda mövcud qeydlər işarələnir ki, istifadəçi onları `drop` edə bilsin. Yazma mərhələsində mövcud qeyd keçilir, sonda keçilən qeydlər haqqında hesabat verilir.

**Dəyişiklik.**

- `engine/vault.py:21-27`: yeni `NoteExistsError(RuntimeError)`, `.slug` və `.category` daşıyır.
- `engine/vault.py:52-56`: `ensure_new(slug)`. Slug hər hansı kateqoriyada varsa, `NoteExistsError` qaldırır.
- `engine/vault.py:59-70`: `write_note(..., replace=False)`. Slug varsa və `replace=False`-dursa, heç nə yazmadan `NoteExistsError` qaldırır. P0-2-nin "köçür" qaydası yalnız `replace=True` ilə qalır.
- `engine/main.py:4-9`: `save_note` `replace`-i `write_note`-a ötürür, defolt `False`-dur.
- `engine/main.py:15-17`: `process` slug-ı `create_note`-dan dərhal sonra hesablayır və `choose_category`-dən **əvvəl** `ensure_new` çağırır.
- `engine/main.py:148-149`: `process_from_plan` slug-ı plan başlığından hesablayır və **heç bir model çağırışından əvvəl** `ensure_new` çağırır.
- `engine/main.py:52-57`, `65`: merge-də yeni ad başqa qeydə aiddirsə, rename təklif olunmur və köhnə ad qalır. `save_note(..., replace=new_slug == target_slug)`: yalnız birləşdirilən qeydin özü əvəz oluna bilər.
- `engine/main.py:82-90`: `notes_on_disk()`. `find_index_drift`-dəki qovluq skanı ayrıca funksiyaya çıxarıldı ki, split planı da ondan istifadə etsin. Dublikatda xəta vermir.
- `engine/cli.py:44-52`, `420-423`: `report_existing`. Adi `kb` dayananda başlığı (fayldan oxunur), kateqoriyanı və yolu göstərir, `kb --merge` təklif edir və `exit(1)` edir.
- `engine/cli.py:141`, `157-165`: plan göstəriləndə mövcud elementlərin yanında `[exists: <kateqoriya>]` yazılır.
- `engine/cli.py:217-221`, `225-230`: yazma mərhələsində `NoteExistsError` tutulur, element keçilir, sonda keçilənlərin siyahısı çap olunur.
- `tests/test_cke.py`: `P0_3_NoOverwriteTests` (8 test). İki P0-2 testi yeniləndi (aşağıda).
- `README.md`: `--split` addımları, `kb` sətri və "Never lose a note" bəndi yeni davranışı təsvir edir.

```diff
-def write_note(slug, category, markdown):
+def write_note(slug, category, markdown, replace=False):
     old_path, old_category = find_note(slug)
+    # Only a merge, which has read the old note into the new text, may replace it. Any other
+    # write would lose the old text: overwritten in the same folder, removed from another one.
+    if old_path is not None and not replace:
+        raise NoteExistsError(slug, old_category)
```

**Niyə bu yanaşma.**

- **Qoruma `write_note`-dadır, çağıranlarda deyil.** Qeydi diskə yazan yeganə yer odur. Ona görə bir yoxlama dörd girişin hamısını bağlayır, gələcəkdə əlavə olunacaq rejim də defolt olaraq qorunur. Əvəz etmək açıq seçimdir (`replace=True`) və onu yalnız merge verir. Merge köhnə qeydi oxuyub yeni mətnə qatır, ona görə orada əvəz etmək itki deyil.
- **Erkən yoxlama (`ensure_new`) təhlükəsizlik üçün yox, xərc üçündür.** `process`-də kateqoriya üçün ikinci API çağırışına qənaət edir. `process_from_plan`-da plan başlığı fayl adının özüdür, ona görə keçilən element üçün heç bir model çağırılmır: hər mövcud qeyd üçün 2 API çağırışı az olur. Son qoruma yenə `write_note`-dadır.
- **`kb` dayanır, `--split` keçir** (Nazirin qərarı). Tək qeyddə dayanmağın qiyməti yoxdur, istifadəçi dərhal `--merge` edə bilər. Split-də isə bir mövcud qeyd 40 qeydlik işi dayandırmamalıdır.
- **Plan daxilindəki təkrar da tutulur.** Model eyni slug verən iki başlıq qaytarsa (`Whois`, `whois`), birincisi yazılır, ikincisi keçilir. İşarələmədə bu görünmür, çünki o anda heç biri diskdə deyil. Amma yazma mərhələsindəki yoxlama onu tutur, bunun üçün ayrıca test var.
- **`--writeup` də dayanır, amma `--merge` təklif etmir.** Nazir iki yol saymışdı, amma `--writeup` və server də eyni funksiyadan keçirdi. Qoruma `write_note`-da olduğu üçün onlar da avtomatik qorunur. `--writeup` üçün `--merge` təklif etmədim, çünki merge `CREATE_SYSTEM`/`MERGE_SYSTEM` ilə işləyir və writeup-u ensiklopediya qeydi kimi yenidən yazardı. Writeup-da başlıq yalnız modelin cavabından sonra bəlli olur, ona görə dayanma API çağırışından sonra baş verir. Mesaj belədir: `ERROR: Note 'box-one' already exists in 90 Writeups. Nothing was written.`
- **Server** eyni mesajı 500 ilə qaytarır. 409 daha dəqiq olardı, amma server legacy-dir və bu dəyişiklik tapşırıqda yox idi.
- **Merge rename-i başqa qeydin adına düşmür.** Yeni ad başqa qeydə aiddirsə, istifadəçidən soruşmağın mənası yoxdur, çünki "yes" cavabı həmin qeydi silərdi. Ona görə sual verilmir və köhnə ad qalır. Bu, P0-1-dəki "təsdiqsiz rename yoxdur" qaydasının davamıdır.
- **CLI mesajları ingiliscədir.** Nazirin nümunəsindəki "mövcud" sözünün əvəzinə `[exists: 08 Tools]` yazılır, çünki CLI-ın qalan bütün çıxışı ingiliscədir.

**P0-2 ilə əlaqə.** P0-2-də "rədd et" variantını adi `kb` sınmasın deyə seçməmişdim. P0-3 bu qərarı yeni qeyd yaratmaq üçün dəyişir: yeni qeyd heç bir kateqoriyada mövcud slug-a yazılmır. "Köçür, sonra yaz" yalnız `replace=True` ilə qalır. Merge həmişə mövcud kateqoriyanı saxladığı üçün bu budaq hazırda heç bir yoldan çağırılmır. "Bir slug = bir fayl" zəmanəti üçün saxlanıb. Buna görə iki P0-2 testi yeniləndi, adları isə dəyişmədi:

- `test_writing_into_a_new_category_moves_the_note`: ikinci yazı `replace=True` ilə edilir.
- `test_reclassified_topic_leaves_no_orphan`: ikinci `kb` rədd olunur, qeyd həm diskdə, həm də index-də `01 Networking`-də qalır.

**Yoxlama.** Yeni testlər əvvəl köhnə kodda, `0eda6b4`-in ayrıca worktree-sində işlədildi. 8 testin hamısı uğursuz oldu (biri subTest ilə iki dəfə):

```
$ (0eda6b4 worktree) python -m unittest discover -s tests -k P0_3 2>&1 | grep -E '^(FAIL|ERROR):|^Ran|^FAILED' | sed -E 's/ \(test_cke\.[^)]*\)//'
ERROR: test_process_stops_before_the_category_call
ERROR: test_write_note_refuses_an_existing_slug_in_any_category (category='08 Tools')
ERROR: test_write_note_refuses_an_existing_slug_in_any_category (category='01 Networking')
ERROR: test_writeup_does_not_replace_an_existing_writeup
FAIL: test_kb_stops_and_suggests_merge
FAIL: test_merge_never_renames_onto_another_note
FAIL: test_split_plan_marks_existing_notes
FAIL: test_split_skips_a_title_repeated_within_the_plan
FAIL: test_split_skips_existing_notes_and_reports_them
Ran 8 tests in 1.259s
FAILED (failures=5, errors=4)
```

`ERROR`-lar `AttributeError`-dur, çünki köhnə kodda `NoteExistsError` yoxdur. Həmin yollarda itkinin özü yuxarıdakı diaqnoz çıxışında görünür. `FAIL`-lar isə birbaşa itkini göstərir. Məsələn, split-də `08 Tools/dig.md` silinib və yerinə `01 Networking/dig.md` yazılıb.

Yeni kodla:

```
$ python -m unittest discover -s tests -v -k P0_3 -k P0_2 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_delete_refuses_an_ambiguous_slug ... ok
test_find_note_reports_a_slug_in_two_categories ... ok
test_reclassified_topic_leaves_no_orphan ... ok
test_writing_into_a_new_category_moves_the_note ... ok
test_kb_stops_and_suggests_merge ... ok
test_merge_never_renames_onto_another_note ... ok
test_process_stops_before_the_category_call ... ok
test_split_plan_marks_existing_notes ... ok
test_split_skips_a_title_repeated_within_the_plan ... ok
test_split_skips_existing_notes_and_reports_them ... ok
test_write_note_refuses_an_existing_slug_in_any_category ... ok
test_writeup_does_not_replace_an_existing_writeup ... ok
Ran 12 tests in 1.257s
OK
```

CLI-ın real çıxışı (sintetik vault, `08 Tools/dig.md` əvvəlcədən var, model mock edilib):

```
$ kb 'dig and whois query dns ...'
--------------------------------------------------
Processing 159 characters with DeepSeek (API)...
Creating new note...
--------------------------------------------------
STOPPED: a note with this filename already exists. Nothing was written.
  title:    DIG
  category: 08 Tools
  file:     08 Tools/dig.md
To add this text to that note, run kb --merge with the same text and pick it from the list.
(exit 1)

$ kb --split 'dig and whois query dns ...'   (answer: Enter)
--------------------------------------------------
Analyzing 159 characters with DeepSeek (API)...

Proposed atomic notes:
  1. dig  [tool]  [exists: 08 Tools]
       DNS lookups
  2. whois  [tool]
       Domain registration data

  [exists] = a note with this filename is already in the vault. It will be skipped, not overwritten.

Options:
  - Press Enter to CREATE all notes as shown
  - Type 'merge 2 3' to combine notes 2 and 3 into one
  - Type 'drop 4' to remove note 4
  - Type 'cancel' to abort
--------------------------------------------------
Creating 2 note(s)...
  skipped (already exists): 08 Tools/dig.md
  created: 01 Networking/whois.md
--------------------------------------------------
Done. Created 1 note(s).
Skipped 1 existing note(s), not overwritten:
  08 Tools/dig.md
```

Sonra vault-da `01 Networking/whois.md` yaradılmışdı, `08 Tools/dig.md`-nin 3-cü sətri isə əvvəlki kimi `Original summary.` idi.

Tam dəst 70 test ilə keçir, real vault round-trip 55/55-dir (aşağıda, "Test xülasəsi").

**Commit:** `3d666a6 fix(P0-3): never overwrite an existing note when creating one`

---

## P1-1 · Index ilə vault uyğun deyildi

**Vəziyyət:** Düzəldildi (kod və vault).

**Diaqnoz.** Index-də 58 yazı var idi, diskdə isə 55 qeyd. 3 yazının faylı yox idi (ghost, yəni "xəyal" yazılar), 1 yazının kateqoriyası isə səhv idi. `kb --merge` ghost yazını namizəd kimi göstərə bilərdi. Onu seçəndə `RuntimeError: Note '...' not found` çıxırdı.

**Dəyişiklik.**

- `engine/main.py:93-110` (`find_index_drift`): yalnız oxuyur. Uyğunsuzluğun dörd növünü qaytarır: `missing_file`, `wrong_category`, `not_indexed`, `duplicate`.
- `engine/main.py:113-126` (`repair_index`): index-i diskə uyğunlaşdırır. Lazım olan bütün embedding-ləri əvvəlcə alır, sonra index-i bir dəfə yazır. Dublikatlara toxunmur.
- `engine/cli.py:267-296` (`handle_reindex`) və `engine/cli.py:310-312`: `kb --reindex` əmri. Əvvəl Ollama yoxlanır, sonra hesabat çap olunur. Dəyişiklik yalnız `yes` cavabından sonra edilir.

**Niyə bu yanaşma.**

- **Defolt olaraq yalnız oxuyur və təsdiq istəyir.** Bu, `kb --delete`-in "yes/no" üslubu ilə eynidir. Ayrıca `--apply` flag-ı da mümkün idi. Amma istifadəçi hər halda dəyişiklik siyahısını görməlidir, sual bunu təbii şəkildə təmin edir.
- **Disk həqiqət mənbəyidir.** Faylın yeri index-dəki kateqoriyadan üstündür, çünki Obsidian və ya Finder-də edilən köçürmə də istifadəçinin qərarıdır.
- **Öz qovluq skanını edir, `find_note`-u çağırmır** (Nazirin əlavəsi). `find_note` dublikat görəndə xəta verir. Reindex də ondan istifadə etsəydi, dublikat yarananda istifadəçi kilidlənərdi: nə diaqnoz qoya, nə də düzəldə bilərdi. İndi skan `list_all_notes()` ilə edilir və dublikatlar `DUPLICATE (fix by hand)` kimi göstərilir.
- **P1-2 əvvəl edildi.** Əks halda skan `Claude outputs/CLAUDE.md` və `PLAN.md` fayllarını da qeyd sayıb index-ə əlavə edərdi. Real hesabatda `add to index` sətrinin olmaması bunun düzgün işlədiyini göstərir.

**Yoxlama.** Testlər:

```
$ python -m unittest discover -s tests -v -k P1_1 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_cli_repairs_after_yes ... ok
test_cli_stops_when_ollama_is_down ... ok
test_cli_writes_nothing_without_yes ... ok
test_duplicate_slug_is_reported_not_guessed ... ok
test_repair_makes_the_index_match_the_disk ... ok
test_report_finds_every_kind_of_drift_and_writes_nothing ... ok
Ran 6 tests in 0.009s
OK
```

Real vault-da Nazirin təsdiqindən sonra işlədildi. Əvvəlki iki xəbərdarlıq P1-3-ə aiddir:

```
$ printf 'yes\n' | ./kb --reindex
--------------------------------------------------
Index entries: 58   Notes on disk: 55
  WARNING (fix by hand): category folder nested inside another: 03 Windows/02 Linux
  WARNING: category folder missing at the top level: 02 Linux
  remove from index (no file on disk): dns-reconnaissance
  remove from index (no file on disk): testbox
  remove from index (no file on disk): whois-lookups
  fix category: web-application-architecture-overview  00 Inbox -> 04 Web

Apply these changes to the index? (yes/no): Index repaired.
```

Saxlanan 55 yazının embedding-i dəyişmədi, yəni yenidən hesablanmadı:

```
index entries: 55 | dims: {768}
web-application-architecture-overview -> 04 Web
ghosts left: []
55/55 entries keep identical vector and title
```

P1-3-dən sonra:

```
$ printf 'no\n' | ./kb --reindex
--------------------------------------------------
Index entries: 55   Notes on disk: 55
Index matches the vault. Nothing to repair.
```

**Commit:** `19cd710 feat(P1-1): add kb --reindex to report and repair index drift`

---

## P1-2 · `Claude outputs/` qeyd kateqoriyası sayılırdı

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `list_all_notes` yalnız nöqtə ilə başlayan qovluqları ötürürdü. Ona görə `Claude outputs/CLAUDE.md` və `PLAN.md` `kb --delete` siyahısında qeyd kimi görünürdü. Onları silmək mümkün idi və bu silmə heç bir iz qoymurdu.

**Dəyişiklik.**

- `engine/config.py:8-16`: kateqoriyalar yalnız bir yerdə saxlanır:
  - `CLASSIFIER_CATEGORIES` (10): classifier-in seçə biləcəyi qovluqlar;
  - `VAULT_CATEGORIES` (13): bunlar üstəgəl `90 Writeups`, `91 Templates`, `99 Archive`.
- `engine/vault.py:4-6` (`category_dirs`): qovluq skanı `VAULT_CATEGORIES`-dən törəyir.
- `engine/vault.py:32`, `engine/main.py:75`: `find_note` və `list_all_notes` `category_dirs()`-dən istifadə edir.
- `engine/brain.py:161`: `choose_category` öz `valid` dəstinin əvəzinə `config.CLASSIFIER_CATEGORIES`-ə baxır.

```diff
-    valid = {
-        "00 Inbox", "01 Networking", "02 Linux", "03 Windows", "04 Web",
-        "05 Active Directory", "06 Cloud", "07 Programming", "08 Tools", "09 Methodology",
-    }
-        if category in valid:
+        if category in config.CLASSIFIER_CATEGORIES:
```

**Niyə bu yanaşma.**

- **Açıq siyahı seçildi, `NN ` prefiksi üçün regex yox.** Siyahıda hansı qovluqların olduğu dəqiq görünür. Qiyməti: Obsidian-da yeni qovluq açılsa (məsələn `10 Crypto`), `config.py`-yə əlavə olunana qədər CLI onu görmür. Bu, `Explanation.md`-nin H bölməsində yazılıb.
- **İki ayrı ad, çünki bunlar iki ayrı dəstdir.** Classifier yalnız 10 kateqoriyadan seçir, skan isə 13 qovluğun hamısını qəbul edir.
- **`CATEGORY_SYSTEM` prompt mətni dəyişmədi.** Mətni sabitdən yaratmaq əvəzinə bir test (`test_prompt_lists_the_same_categories_as_config`) yazdım. O, prompt-dakı siyahının `config` ilə eyni qalmasını yoxlayır.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P1_2 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_choose_category_only_accepts_classifier_targets ... ok
test_classifier_and_vault_category_lists ... ok
test_find_note_ignores_non_category_folders ... ok
test_list_all_notes_ignores_non_category_folders ... ok
test_prompt_lists_the_same_categories_as_config ... ok
Ran 5 tests in 0.002s
OK
```

Real vault-da (yalnız oxuma):

```
list_all_notes(): 55 notes; categories: ['01 Networking', '04 Web', '08 Tools', '09 Methodology']
CLAUDE/PLAN listed: []
```

**Commit:** `c7cecd7 fix(P1-2): only real category folders hold notes`

---

## P1-3 · `02 Linux` qovluğu `03 Windows`-un içində idi

**Vəziyyət:** Düzəldildi (kod və vault).

**Diaqnoz.** Vault-da `03 Windows/02 Linux/` boş qovluğu var idi, yuxarı səviyyədə isə `02 Linux` yox idi. Classifier ilk dəfə `02 Linux` seçəndə `write_note` yuxarıda ikinci `02 Linux` yaradacaqdı. Nəticədə eyni kateqoriya iki yerdə olacaqdı.

**Dəyişiklik.**

- `engine/vault.py:9-18` (`check_layout`): iki siyahı qaytarır. Birincisi yuxarı səviyyədə olmayan classifier kateqoriyalarıdır, ikincisi başqa kateqoriyanın içində olan kateqoriya qovluqlarıdır.
- `engine/cli.py:274-278`: `kb --reindex` bunları xəbərdarlıq kimi göstərir.
- Vault-da Nazirin təsdiqindən sonra qovluqlar düzəldildi.

**Niyə bu yanaşma.** Yoxlama yalnız hesabat verir və avtomatik heç nə düzəltmir. Vault-da qovluq köçürmək istifadəçinin qərarıdır. Bu həm də birdəfəlik işdir. Yoxlama maintenance (texniki baxım) əmrinə qoyuldu, hər işə salınmada yox: adi `kb` işini yavaşlatmasın və hər dəfə eyni xəbərdarlıqla mane olmasın.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P1_3 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_clean_layout_reports_nothing ... ok
test_reports_nested_and_missing_category_folders ... ok
Ran 2 tests in 0.003s
OK
```

```
$ cd ~/Documents/CyberKB && ls -la "03 Windows/02 Linux" && rmdir "03 Windows/02 Linux" && echo "rmdir: OK" && mkdir "02 Linux" && echo "mkdir: OK"
total 0
drwxr-xr-x@ 2 nazir  staff  64 30 Sep 22:56 .
drwxr-xr-x@ 3 nazir  staff  96 30 Sep 22:56 ..
rmdir: OK
mkdir: OK
```

Qovluq boş idi, `.DS_Store` da yox idi. Sandbox `rmdir`-i bloklamadı.

**Commit:** `d9cd67c feat(P1-3): check that category folders are top-level and not nested`

---

## P1-4 · Ollama API rejimində də lazımdır, amma yalnız lokal rejimdə yoxlanırdı

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** Embedding həmişə Ollama-dan alınır, hətta qeydi DeepSeek yazanda da. Amma `check_ollama` yalnız `--local` ilə çağırılırdı. API rejimində Ollama sönülü olanda DeepSeek çağırışları uğurla bitirdi, fayl diskə yazılırdı, sonra isə `memory.update_entry`-də `ConnectionError` baş verirdi. Nəticədə fayl diskdə qalırdı, amma index-ə heç vaxt düşmürdü. Bu, P1-1-dəki uyğunsuzluğun ehtimal olunan mənbəyidir. Bundan başqa, `check_ollama` istənilən HTTP cavabını, hətta 404-ü də "OK" sayırdı.

**Dəyişiklik.** Qoruma iki qatdan ibarətdir.

1. **CLI-da yoxlama** (`engine/cli.py:11-32`, `engine/cli.py:306-308`):
   - `require_ollama()` `--delete`-dən başqa hər rejimdə, hər iki backend-də (modelin işlədiyi yer) ən əvvəl çağırılır.
   - `check_ollama` HTTP 200 tələb edir və `config.EMBED_MODEL`-in `/api/tags`-də olub-olmadığını yoxlayır. Tag nəzərə alınmadan müqayisə edir: `nomic-embed-text` == `nomic-embed-text:latest`.
2. **Yazma sırası** (Nazirin düzəlişi). `memory.update_entry` iki funksiyaya bölündü: `embed_entry` (şəbəkə, `engine/memory.py:24-30`) və `save_entry` (disk, `engine/memory.py:33-36`). Bütün yazma yolları `main.save_note`-dan keçir (`engine/main.py:4-9`):

```python
def save_note(slug, category, note):
    # 1) embedding (network: Ollama may be down)  2) note file  3) index entry.
    # If the network step fails nothing is written; the two disk writes happen side by side.
    entry = memory.embed_entry(note.title, note.summary, category)
    vault.write_note(slug, category, vault.to_markdown(note))
    memory.save_entry(slug, entry)
```

`process`, `process_from_plan`, `process_writeup` və `merge_into` (`engine/main.py:23, 141, 149, 55`) bu funksiyanı çağırır. `repair_index` də eyni prinsiplə işləyir: əvvəl bütün embedding-lər alınır, index sonra yazılır.

**Niyə bu yanaşma.**

- **İki qat birlikdə.** CLI yoxlaması DeepSeek-ə pul xərclənməzdən əvvəl işləyir və aydın mesaj verir. Yazma sırası isə server kimi CLI-dan keçməyən yolları da qoruyur.
- **Sıra: embedding → fayl → index.** Uğursuzluq ehtimalı ən yüksək olan addım şəbəkə addımıdır, ona görə o birinci gəlir. O uğursuz olsa, heç nə yazılmır. İki disk əməliyyatı yan-yana, şəbəkədən sonra gəlir.
- **Rədd edilən variant 1: mənim ilk təklifim (index → fayl).** Nazir göstərdi ki, bu tərs problem yaradır. Index yazılsa və fayl yazısı uğursuz olsa, index-də ghost yazı qalar. Bu, P1-1-də təmizlədiyimiz vəziyyətin özüdür. Bunu yoxlamaq üçün `test_failed_file_write_leaves_no_ghost_index_entry` testi əlavə edildi.
- **Rədd edilən variant 2: "index alınmasa, yazılmış faylı sil" (rollback).** Rename olmayan merge-də yeni fayl köhnəsinin üzərinə yazılır. Rollback-də silinən fayl **orijinal qeydin özü** olardı.
- **`--delete` istisnadır**, çünki embedding lazım deyil. Silmə Ollama işləməsə də mümkün olmalıdır.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P1_4 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_delete_does_not_need_ollama ... ok
test_every_write_mode_stops_before_any_work ... ok
test_failed_file_write_leaves_no_ghost_index_entry ... ok
test_merge_leaves_the_original_untouched ... ok
test_process ... ok
test_process_from_plan ... ok
test_process_writeup ... ok
test_embedding_model_is_found_with_or_without_tag ... ok
test_http_error_is_not_ok ... ok
test_missing_embedding_model_is_not_ok ... ok
test_unreachable_is_not_ok ... ok
Ran 11 tests in 0.006s
OK
```

Canlı Ollama ilə yoxlama. Bu, real sorğudur, heç nə yazmır:

```
check_ollama() with EMBED_MODEL 'nomic-embed-text' -> True
check_ollama() with EMBED_MODEL 'not-a-pulled-model' -> False
check_ollama() against a 404 URL -> False
```

Ollama "sönülü" olanda (yanlış port, sintetik vault):

```
ERROR: Ollama is not reachable at http://localhost:1, or the embedding model 'nomic-embed-text' is not pulled. Start Ollama, then run: ollama pull nomic-embed-text
exit=1
.md files written: 0
```

**Commit:** `09f4e9d fix(P1-4): check Ollama before every write mode, never leave a note unindexed`

---

## P1-5 · Schema `None`, `dict` və rəqəmləri bölmə məzmunu kimi qəbul edirdi

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `content_to_string` hər şeyə `str()` tətbiq edirdi. `None` dəyəri `"None"` mətninə çevrilirdi və `content_not_empty` heç vaxt işə düşmürdü. Validation uğurlu sayıldığı üçün `brain.py`-dəki retry (təkrar cəhd) döngüsü də işləmirdi. Qeydə sözün həqiqi mənasında "None" sözü yazılırdı.

**Dəyişiklik.** `engine/schema.py:25-38`:

```diff
     def content_to_string(cls, v):
+        if isinstance(v, str):
+            return v
         if isinstance(v, list):
+            for item in v:
+                # bool is a subclass of int, so it has to be excluded explicitly
+                if isinstance(item, bool) or not isinstance(item, (str, int, float)):
+                    raise ValueError(f"content list items must be strings or numbers, got {type(item).__name__}")
             return "\n".join(f"- {item}" for item in v)
-        return str(v)
+        raise ValueError(f"content must be a string or a list of strings, got {type(v).__name__}")
```

**Niyə bu yanaşma.**

- **Qəbul edilənlər: `str` və `list[str|int|float]`** (Nazirin qərarı). İlk planım siyahıda yalnız string qəbul etmək idi. Nazir bunu yumşaltdı: `- 80`, `- 443` mənalı bullet-lərdir. Model port siyahısını rəqəm kimi qaytaranda retry etmək mənasız API xərci olardı.
- **`bool` ayrıca istisna edilir**, çünki Python-da `bool` `int`-in alt sinfidir (`isinstance(True, int)` `True` qaytarır).
- **Səhv mesajı konkretdir.** Mesaj retry prompt-una (`engine/brain.py:118`) olduğu kimi gedir və model nəyi düzəltməli olduğunu görür. Title/body aliası və `fill_missing_summary` dəyişmədi.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P1_5 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_missing_summary_is_still_filled_from_title ... ok
test_numbers_in_a_list_become_bullets ... ok
test_rejects_bad_list_items ... ok
test_rejects_non_text_content ... ok
test_still_accepts_strings_and_lists ... ok
test_still_rejects_empty_values ... ok
test_title_and_body_aliases_still_work ... ok
Ran 7 tests in 0.000s
OK
```

Retry prompt-unun alacağı mesaj:

```
1 validation error for Note
sections.0.content
  Value error, content must be a string or a list of strings, got NoneType [type=value_error, input_value=None, input_type=NoneType]
```

**Commit:** `aa17a1d fix(P1-5): reject non-text section content instead of stringifying it`

---

## P1-6 · `slugify` boş sətir qaytara bilirdi

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `slugify("..")`, `slugify("日本語")`, `slugify("!!!")` boş sətir qaytarırdı. `write_note` bu halda `<kateqoriya>/.md` adlı gizli fayl yaradırdı, index-də isə açar `""` olurdu.

**Dəyişiklik.**

- `engine/vault.py:79-94`: nəticə boş qalanda `untitled-` + başlığın SHA-256 heşinin ilk 8 simvolu qaytarılır.
- `engine/main.py:45-46`: `merge_into` `fallback=False` ilə çağırır.

```diff
-def slugify(title):
+def slugify(title, fallback=True):
 ...
-    return "-".join(words)
+    slug = "-".join(words)
+    if not slug and fallback:
+        slug = "untitled-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
+    return slug
```

**Niyə bu yanaşma.**

- **Qayda deterministikdir və izlənə bilir.** Eyni başlıq həmişə eyni fayl adını verir. Ad təsadüfi deyil, onu başlıqdan yenidən hesablamaq olar.
  - Rədd etdim: təsadüfi və ya `uuid` əsaslı ad, çünki deterministik deyil.
  - Rədd etdim: unicode transliterasiyası (məsələn `é` → `e`). Bu, mövcud qeydlərin slug-unu dəyişərdi.
- **Merge `fallback=False` ilə çağırır.** Modelin qaytardığı yararsız başlıq qeydin `untitled-...` adına dəyişməsinə səbəb olmamalı, merge-i dayandırmalıdır. Bu, P0-1-in tələbidir.
- **Köhnə davranış dəyişmədi.** 8 sözlük kəsmə və nöqtələrin, `/` simvollarının silinməsi olduğu kimi qaldı. Real vault-dakı 55 qeydin hamısı yenə öz fayl adına uyğun gəlir.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P1_6 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_fallback_is_deterministic_and_distinct ... ok
test_normal_titles_are_unchanged ... ok
test_slug_is_never_empty_or_unsafe ... ok
test_strict_mode_reports_an_unusable_title ... ok
Ran 4 tests in 0.000s
OK
```

```
'..'                   -> 'untitled-5ec1f7e7'
'日本語'                  -> 'untitled-77710aed'
'!!!'                  -> 'untitled-e84c538e'
'   '                  -> 'untitled-0aad7da7'
'-'                    -> 'untitled-3973e022'
'../../etc/passwd'     -> 'etcpasswd'
=== all 55 real note titles keep their slug? (read-only)
title->slug mismatches: 0 []
```

**Commit:** `c64b9cc fix(P1-6): never produce an empty slug`

---

## P1-7 · `API_MODEL` sənədləşdirilməmiş alias idi

Bu bənd tapşırıqda yox idi. §0.3-dəki yoxlama zamanı tapıldı və Nazir onu yeni bənd kimi əlavə etdi.

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `config.API_MODEL = "deepseek-v4-flash"` idi. `GET /models` yalnız `deepseek-flash` və `deepseek-v4-pro` qaytarır. `deepseek-v4-flash` hələ də qəbul olunur, amma cavab `deepseek-flash` modelindən gəlir. Yəni bu, sənədləşdirilməmiş alias-dır (əlavə ad). Tarixçədə model id-si əvvəl NVIDIA formatında idi: `910dfd8`-də `deepseek-ai/deepseek-v4-flash`.

**Dəyişiklik.** `engine/config.py:42`:

```diff
-API_MODEL = "deepseek-v4-flash"
+API_MODEL = "deepseek-flash"
```

**Niyə bu yanaşma.** DeepSeek alias-ı xəbərdarlıq etmədən silə bilər. O zaman **API rejimi tamamilə sınar**: bütün rejimlərdə hər `kb` əmri model çağırışında xəta verər. Rəsmi id isə `/models` siyahısındadır. Dəyişiklik bir sətirlikdir və ayrıca commit-də edildi ki, lazım olsa asanlıqla geri qaytarılsın.

**Yoxlama.** 2026-10-12-də hər iki ad işləyirdi. Açarın dəyəri heç yerdə çap olunmayıb:

```
API_BASE_URL: https://api.deepseek.com
models returned: ['deepseek-flash', 'deepseek-v4-pro']
config.API_MODEL = 'deepseek-v4-flash' -> NOT PRESENT

'deepseek-v4-flash': OK -> response.model = 'deepseek-flash'
'deepseek-flash': OK -> response.model = 'deepseek-flash'
```

**Commit:** `2a2e62a fix(P1-7): use official deepseek-flash model id`

---

## P2-1 · `--split` planı yoxlanmırdı

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `propose_split` modelin qaytardığı xam `notes` siyahısını birbaşa ötürürdü, CLI isə `note['title']`-i birbaşa oxuyurdu. Başlığı olmayan plan elementi `KeyError` ilə prosesi sındırırdı. README isə "model output is validated" deyirdi, yəni `--split` üçün bu iddia doğru deyildi.

**Dəyişiklik.**

- `engine/schema.py:48-64`: `PlanEntry` (`title` məcburidir və boş ola bilməz; `type`, `covers`, `source_hint` istəyə bağlı string-lərdir) və `SplitPlan`.
- `engine/brain.py:112`: `generate_validated`-ə `schema` parametri əlavə edildi, defolt `Note`-dur.
- `engine/brain.py:203-206`: `propose_split` həmin retry yolundan keçir.

```diff
-def generate_validated(system, prompt, backend=None):
+def generate_validated(system, prompt, backend=None, schema=Note):
 ...
-            return Note.model_validate(raw)
+            return schema.model_validate(raw)
 ...
 def propose_split(text, backend=None):
-    result = llm.ask_json(SPLIT_SYSTEM, text, backend=backend)
-    return result.get("notes", [])
+    plan = generate_validated(SPLIT_SYSTEM, text, backend=backend, schema=SplitPlan)
+    return [entry.model_dump() for entry in plan.notes]
```

**Niyə bu yanaşma.**

- **Notlar üçün olan retry yolu təkrar istifadə olunur.** Yeni retry məntiqi yazılmadı.
- **Plan dict kimi qaytarılır.** `cli.py` və `main.py` heç dəyişmədən işləməyə davam edir.
- **Rədd etdim: yararsız elementləri səssizcə atmaq.** İstifadəçi bir mövzunun itdiyini heç vaxt bilməzdi. Retry modelə səhvi düzəltmək imkanı verir. Son cəhd də uğursuz olsa, CLI `ERROR during planning` çap edir və heç nə yazmır. `SPLIT_SYSTEM` prompt mətni dəyişmədi.

**Yoxlama.** Köhnə kodda (düzəliş müvəqqəti geri götürülmüşdü) testlər audit-in təsvir etdiyi xəta ilə sınırdı:

```
ERROR: test_a_retry_can_fix_the_plan
    -> KeyError: 'title'
ERROR: test_cli_prints_the_error_and_saves_nothing
    -> KeyError: 'title'
FAIL: test_malformed_plans_are_reported_not_crashed_on (response={'notes': [{'covers': 'no title'}]})
    -> AssertionError: RuntimeError not raised
```

Yeni kodda:

```
$ python -m unittest discover -s tests -v -k P2_1 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_a_retry_can_fix_the_plan ... ok
test_cli_prints_the_error_and_saves_nothing ... ok
test_malformed_plans_are_reported_not_crashed_on ... ok
test_valid_plan_fills_optional_fields ... ok
Ran 4 tests in 0.159s
OK
```

**Commit:** `4aee124 fix(P2-1): validate the --split plan through the schema retry path`

---

## P2-2 · `chunker.py` tamamilə ölü kod idi

**Vəziyyət:** Düzəldildi (modul silindi).

**Diaqnoz.** `chunker.py`-ni heç bir modul import etmirdi. Üç funksiyası yalnız bir-birini çağırırdı. Modulda iki parser xətası da var idi: `####` başlıqları tanınmırdı, fence-in içindəki `# comment` isə başlıq sayılırdı.

**Dəyişiklik.** `engine/chunker.py` silindi (60 sətir). README-də bu modulun adı keçmirdi.

**Niyə bu yanaşma.** Modulu `--split`-ə qoşmaq üç iş tələb edərdi: hər iki xətanı düzəltmək, `config.py`-yə token həddi əlavə etmək və testlər yazmaq. `--split` isə mətni onsuz da bütöv halda modelə göndərir və hazırda böyük mətnlə bağlı ölçülmüş problem yoxdur. Rəyçi itkin funksiyadan tez ölü kodu görür. Lazım olsa, kod git tarixçəsindədir.

**Yoxlama.**

```
$ grep -rn "chunker" --include='*.py' --include='*.md' --include='*.sh' --include='*.txt' . | grep -v '^./venv\|^./archive\|^./CKE-TASK.md'
(boş, heç bir istinad qalmayıb)
$ python -m unittest discover -s tests
OK (skipped=1)
```

**Qeyd (2026-10-13, yekunlaşdırıldı 2026-10-16):** silinmə qərarı əvvəlcə Nazirin gələcək planını bilmədən verilmişdi: Nazir modulu 100K sözlük girişlər üçün saxlayırdı. Bu plan yoxlanmamış "128K kontekst" rəqəminə əsaslanırdı. 2026-10-16-da DeepSeek-in sənədi ilə 1M kontekst təsdiqləndi: `deepseek-flash` DeepSeek-V4.1-Flash-dır, kontekst 1M token, maksimum çıxış 384K token (https://api-docs.deepseek.com/quick_start/pricing). Nazirin ən böyük modulu ~175K tokendir və bir çağırışa rahat sığır, ona görə chunker-ə ehtiyac qalmadı. **Silinmə qərarı qətidir.** Modul yalnız git tarixçəsində qalır (`git show 65d8b47^:engine/chunker.py`).

**Commit:** `65d8b47 refactor(P2-2): delete unused chunker module`

---

## P2-3 · Daha üç istifadə olunmayan funksiya

**Vəziyyət:** Düzəldildi (hər üçü silindi).

**Diaqnoz.** `brain.decide_same_topic` (`DECISION_SYSTEM` ilə birlikdə), `vault.note_path` və `vault.note_exists` heç yerdən çağırılmırdı.

**Dəyişiklik.** `engine/brain.py`-dən 15 sətir silindi (`DECISION_SYSTEM` + `decide_same_topic`). `engine/vault.py`-dən 9 sətir silindi (`note_path`, `note_exists`). Commit-də heç bir sətir əlavə olunmayıb, digər prompt-lara toxunulmayıb.

**Niyə bu yanaşma.** `decide_same_topic`-i `--merge`-ə qoşmaq üçün hər namizədin `summary`-si lazım idi. Index isə yalnız `vector`, `title`, `category` saxlayır. Deməli hər namizəd qeydi diskdən oxunmalı olardı. Tapşırıq yarımçıq qoşmaq əvəzinə silməyi tövsiyə edir. `--merge` embedding həddinə və istifadəçinin seçiminə əsaslanır, README də bunu belə təsvir edir.

**Yoxlama.**

```
$ grep -rn "decide_same_topic\|DECISION_SYSTEM\|note_path\|note_exists" engine/ tests/ README.md || echo "no references left"
no references left
```

**Commit:** `243f44a refactor(P2-3): delete unused decide_same_topic, note_path, note_exists`

---

## P2-4 · `config.DEFAULT_BACKEND` heç nəyə təsir etmirdi

**Vəziyyət:** Düzəldildi.

**Diaqnoz.** `cli.py`-də `backend = "api"` birbaşa yazılmışdı. `config.py`-də `DEFAULT_BACKEND`-i dəyişmək CLI-a heç bir təsir etmirdi.

**Dəyişiklik.** `engine/cli.py:314`:

```diff
-    backend = "api"
+    backend = config.DEFAULT_BACKEND
```

`--local` hələ də onu üstələyir. Server isə bu dəyəri əvvəldən də istifadə edirdi: `ask_json`-un `backend=None` qolu vasitəsilə.

**Yoxlama.** Köhnə kodda:

```
FAIL: test_default_comes_from_config
AssertionError: 'api' != 'local'
```

Yeni kodda:

```
$ python -m unittest discover -s tests -v -k P2_4 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_default_comes_from_config ... ok
test_local_flag_overrides_config ... ok
Ran 2 tests in 0.467s
OK
```

**Commit:** `b541037 fix(P2-4): make config.DEFAULT_BACKEND drive the CLI`

---

## P2-5 · Vault yolunu dəyişmək mümkün deyildi

**Vəziyyət:** Düzəldildi. Bu bənd testlərdən əvvəl edildi (§0.4).

**Dəyişiklik.** `engine/config.py:4-5`:

```diff
+import os
 from pathlib import Path

-VAULT = Path.home() / "Documents" / "CyberKB"
+# CKE_VAULT overrides the vault location (per machine, and for the tests)
+VAULT = Path(os.environ.get("CKE_VAULT") or Path.home() / "Documents" / "CyberKB").expanduser()
 INDEX_FILE = VAULT / ".kb_index.json"
```

**Niyə bu yanaşma.**

- **`or` operatoru:** boş `CKE_VAULT=` dəyəri defolt yola qayıdır. Əks halda boş yol cari qovluğu vault sayardı.
- **`expanduser()`:** dırnaq içində yazılmış `~` da düzgün açılır.
- **`INDEX_FILE` hələ də `VAULT`-dan törəyir.**
- **Məhdudiyyət:** `CKE_VAULT` `.env`-dən **oxunmur**. `config` modulu `load_dotenv`-dən (`engine/llm.py:11`) əvvəl import olunur. Ona görə bu dəyişən shell-də təyin olunmalıdır. README-də də belə yazılıb.

**Yoxlama.** Scratchpad yolu `<scratchpad>` kimi qısaldılıb, qalanı real çıxışdır:

```
### default (CKE_VAULT unset)
VAULT      = /Users/nazir/Documents/CyberKB
INDEX_FILE = /Users/nazir/Documents/CyberKB/.kb_index.json
### CKE_VAULT=<scratchpad>/fakevault
VAULT      = <scratchpad>/fakevault
INDEX_FILE = <scratchpad>/fakevault/.kb_index.json
### CKE_VAULT='' (empty -> default)
VAULT      = /Users/nazir/Documents/CyberKB
### CKE_VAULT='~/kbtest' (quoted tilde)
VAULT      = /Users/nazir/kbtest
### code path: list_all_notes() on a synthetic vault
[('synthetic', '08 Tools')]
```

**Commit:** `9e30936 feat(P2-5): allow CKE_VAULT environment override for vault path`

---

## P2-6 · Flask server bütün interfeyslərdə autentifikasiyasız dinləyirdi

**Vəziyyət:** Düzəldildi. Token yolu kodda hazırdır, amma qurulması Nazirin qərarı ilə təxirə salındı.

**Diaqnoz.** `app.run(host="0.0.0.0", port=8000)` idi. `/note` şəbəkədəki istənilən cihazdan JSON qəbul edir və onu birbaşa `process()`-ə, oradan LLM-ə və vault-a ötürür. Yeganə yoxlama `len(text) < 30` idi.

Yoxlama zamanı tapdıqlarım:

- Server-i `~/Library/LaunchAgents/com.cke.server.plist` işə salır (`KeepAlive`, `RunAtLoad`, stdout və stderr `~/cke/server.log`-a yazılır).
- Server **hazırda işləyir**: PID 869, `*:8000`, yaddaşda köhnə kod.
- `server.log` 3 337 053 baytdır. Audit 30 başlanğıc demişdi, mən isə **7478 başlanğıc banneri** saydım. Bunlardan 7448-i `Address already in use` ilə bitib. Bu, crash-restart döngüsünü göstərir: port artıq məşğul olanda launchd server-i hər dəfə yenidən başladıb.

**Dəyişiklik.**

- `engine/config.py:34-38`: `SERVER_HOST = "127.0.0.1"`, `SERVER_PORT = 8000`.
- `engine/server.py:9-20` (`authorized`): server localhost-da deyilsə, `/note` `Authorization: Bearer <CKE_SERVER_TOKEN>` tələb edir. Müqayisə `hmac.compare_digest` ilə aparılır. Token olmasa və ya səhv olsa, 401 qaytarılır.
- `engine/server.py:51-59`: başlanğıc banneri real hostu göstərir.

```diff
-    print("Listening on all interfaces, port 8000")
+    print(f"Listening on {config.SERVER_HOST}, port {config.SERVER_PORT}")
 ...
-    app.run(host="0.0.0.0", port=8000)
+    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT)
```

**Niyə bu yanaşma.**

- **Localhost defoltdur (Nazirin seçimi: (a) variantı).** Bu, təhlükəni dərhal aradan qaldırır.
- **Token yolu niyə təxirə salındı:** M1 client pipeline hazırda real istifadədə deyil, CKE-TASK §5 də `server.py`-ı legacy sayır. Public bind + token qurmaq indi lazımsız işdir. M1 tərəfi işə düşəndə server onsuz da yenidən yazılmalı olacaq, çünki `--split` və `--writeup`-ı dəstəkləmir. Token yoxlaması kodda var və testlənib. Onu açmaq üçün `SERVER_HOST`-u dəyişib `.env`-ə token əlavə etmək kifayətdir.
- **Public rejimdə token yoxdursa, server çıxmır, hər sorğunu rədd edir.** Səbəb launchd-nin `KeepAlive` parametridir. Çıxan server-i launchd hər 10 saniyədən bir yenidən başladardı və log yenidən crash döngüsü ilə dolardı (yuxarıdakı 7448 sətir kimi).
- **`hmac.compare_digest`** sabit vaxtda müqayisə edir. Adi `==` isə uyğunsuzluğun hansı simvolda başladığını cavab vaxtı ilə sızdıra bilər.
- **Log rotation kodda edilmədi.** `server.log`-u Python yox, launchd açır (`StandardOutPath`). Python-dakı `RotatingFileHandler` bu fayla təsir etməz. Manual addım aşağıda, "Manual addımlar" bölməsindədir.
- **Məlum məhdudiyyət:** server yalnız `process`-i import edir, yəni yalnız adi qeyd yarada bilir, `--split` və `--writeup` edə bilmir. Bu, tapşırığa uyğun olaraq olduğu kimi saxlanıldı.

**Yoxlama.**

```
$ python -m unittest discover -s tests -v -k P2_6 2>&1 | grep -E ' \.\.\. |^Ran|^OK' | sed -E 's/ \(test_cke\.[^)]*\)//'
test_default_binds_to_localhost ... ok
test_localhost_needs_no_token ... ok
test_public_server_accepts_the_right_token ... ok
test_public_server_rejects_missing_or_wrong_token ... ok
test_public_server_without_configured_token_accepts_nothing ... ok
Ran 5 tests in 0.031s
OK
```

```
LOCAL_ONLY = True | host = 127.0.0.1 | token configured = False
```

**Diqqət:** işləyən server (PID 869) yenidən başladılana qədər köhnə kodla `*:8000`-də qalır. Mən onu yenidən başlatmadım, bu, Nazirin addımıdır.

**Commit:** `7128787 fix(P2-6): bind the server to localhost, require a token when public`

---

## P2-7 · `cli.py`-də girinti və sətir sonu boşluqları

**Vəziyyət:** Düzəldildi.

**Dəyişiklik.** `--split` blokunda (`engine/cli.py:320-330`) 3 boşluqluq girinti 4 boşluğa düzəldildi. 4 sətirdə sətir sonundakı boşluqlar silindi. `--split` blokundan sonrakı üç boş sətir bir sətrə endirildi, digər bloklarda olduğu kimi.

**Yoxlama.** Məntiq dəyişməyib:

```
$ git diff -w --ignore-blank-lines engine/cli.py | grep -E '^[-+][^-+]' || echo "(no non-whitespace changes: logic untouched)"
(no non-whitespace changes: logic untouched)
trailing-whitespace lines left: 0
3-space-style lines left: 0
OK (skipped=1)
```

**Commit:** `a7de9dd style(P2-7): fix indentation and trailing whitespace in cli.py`

---

## P3-1 · README bütün Markdown sintaksisini itirmişdi

**Vəziyyət:** Düzəldildi.

**Dəyişiklik.**

- README real Markdown ilə yenidən yazıldı: başlıqlar, pipe cədvəllər, diaqram və əmrlər üçün fence-lər.
- Mövcud məzmun və üslub saxlanıldı.
- Setup bölməsi əlavə olundu: clone, venv, `pip`, Ollama modelləri, `.env`, `CKE_VAULT`, `kb` alias-ı.
- Düzəldilmiş kodu təsvir edən hissələr əlavə olundu: Ollama `--delete`-dən başqa hər rejimdə lazımdır, `kb --reindex`, `kb --file`, merge-də rename təsdiqi, server-in localhost defoltu və tokeni, test əmri.

**`kb` necə qurulub (yoxlanıldı, güman edilmədi):**

```
$ zsh -ic 'type kb'
kb is an alias for /Users/nazir/cke/kb
$ grep -nE 'alias kb=' ~/.zshrc
122:alias kb="/tam/yol/cyber-knowledge-engine/kb"
123:alias kb="/tam/DDDDyol/cyber-knowledge-engine/kb"
124:alias kb="/Users/nazir/cke/kb"
```

- `kb-local.sh` heç yerdən çağırılmırdı: nə alias, nə launchd, nə də kod. Nazirin qərarı ilə **silindi**. Onun yeganə əlavə funksiyası (`nano` açmaq) `kb --file <path>` ilə əvəz olunur. README indi `--file` yolunu izah edir.
- `~/.zshrc`-dəki 122–123-cü sətirlər köhnə placeholder-lərdir və 124-cü sətir onları üstələyir. Nazirin göstərişi ilə `~/.zshrc`-ə **toxunulmadı**.

**Yoxlama.** Audit-in istifadə etdiyi ölçülər:

```
                          əvvəl   indi
lines starting with '#' :   0      15
lines containing '|'    :   0      17
code fences '```'       :   0      20
tab-separated lines     :  11       0
diagram preserved byte-for-byte? diagram: IDENTICAL
```

README-də `chunker`, `decide_same_topic` və ya `deepseek-v4-flash` adı keçmir.

**Commit:**
- `41f16db docs(P3-1): restore README markdown and add setup instructions`
- `9b4d2f8 chore(P3-1): remove unused kb-local.sh launcher`

---

## P3-2 · LICENSE sahibi

**Vəziyyət:** Düzəldildi (Nazirin cavabından sonra).

```diff
-Copyright (c) 2025 VoxZen
+Copyright (c) 2026 Mirnazir Babazade
```

**Commit:** `d5a6e4b docs(P3-2): set LICENSE holder to legal name and current year`

---

## P3-3 · GitHub topics

**Vəziyyət:** Fayl dəyişikliyi deyil, Nazirin manual addımıdır (aşağıya baxın).

---

## Vault dəyişiklikləri

`~/Documents/CyberKB`-də edilən bütün dəyişikliklər. Hər biri Nazirin təsdiqindən sonra edilib.

| # | Dəyişiklik | Yol | Növ | Qeydlər (əvvəl → sonra) | Index yazıları (əvvəl → sonra) |
|---|---|---|---|---|---|
| 1 | 1-ci sətirdəki artıq tab silindi (4672 → 4671 bayt) | `01 Networking/dns-record-types.md` | dəyişdirildi | 55 → 55 | 58 → 58 |
| 2 | 3 ghost yazı silindi, 1 kateqoriya düzəldildi | `.kb_index.json` | dəyişdirildi | 55 → 55 | 58 → 55 |
| 3 | Boş iç-içə qovluq silindi | `03 Windows/02 Linux/` | silindi | 55 → 55 | 55 → 55 |
| 4 | Yuxarı səviyyədə kateqoriya qovluğu yaradıldı | `02 Linux/` | yaradıldı | 55 → 55 | 55 → 55 |

Heç bir qeyd yaradılmadı, adı dəyişdirilmədi və ya silinmədi. `dns-record-types.md` vault-un git-ində izlənmir. Onu bərpa etmək üçün yeganə mənbə aşağıdakı arxivdir.

## Backup

| Fayl | Yoxlama |
|---|---|
| `~/Desktop/CyberKB-prefix-20261012-2215.tar.gz` (969 481 bayt) | `tar -tzf \| wc -l` = **285**, `grep -c '\.md$'` = **58** (55 qeyd + `Claude outputs/PLAN.md`, `Claude outputs/CLAUDE.md`, `.claude/commands/teach.md`). `gzip -t`: OK. Arxiv açılıb canlı vault ilə `diff -r` ilə müqayisə edildi: **IDENTICAL** |
| `~/Desktop/kb_index-prefix.json` | SHA-256 `0784a94d9fc83f02005b233772a39c33a8f9dc7947f4342d559827f785bc0cef` (orijinal ilə eyni), 58 yazı, 768 ölçü, sıfır vektor yoxdur |

## Xaricdə yoxlanılanlar (§0.3)

| Yoxlama | Nəticə |
|---|---|
| Ollama quraşdırılıb? | Bəli, `ollama version is 0.24.0`. `/api/tags` HTTP 200 qaytarır |
| `qwen3:14b` var? | Bəli |
| `nomic-embed-text` var? | Bəli, `nomic-embed-text:latest` kimi. `llm.embed()` real çağırışda **768** ölçülü vektor qaytardı, index ilə uyğundur |
| `API_MODEL` düzgündür? | `deepseek-v4-flash` işləyirdi, amma `/models`-də yox idi (alias). **P0 deyil**, çünki sistem işləyirdi. P1-7 kimi düzəldildi və `deepseek-flash`-a keçirildi |

## Test xülasəsi

- **70 test**, hamısı keçir. İzolyasiya olunmuş işlədilmədə 1 test skip olunur (real vault testi).
- Real vault ilə: **70/70 OK**, round-trip **55/55**. Bu test vault-u yalnız oxuyur.

```
$ cd ~/cke && source venv/bin/activate && python -m unittest discover -s tests
----------------------------------------------------------------------
Ran 70 tests in 2.006s

OK (skipped=1)

$ CKE_VAULT=~/Documents/CyberKB python -m unittest discover -s tests
real vault round trip: 55/55 notes keep title, headings and every code line
Ran 70 tests in 1.996s
OK
```

Testlər Python 3.11 və ya daha yeni versiya tələb edir (`TestCase.enterContext`). Layihə 3.14 üzərində hazırlanıb.

## Hələ açıq qalanlar

Bunları tapdım, amma düzəltmədim. Ya tapşırıqda yox idi, ya da qərar Nazirindir.

1. **Index atomik yazılmır.** `memory.save_index` faylı birbaşa `write_text` ilə yazır. Yazma yarıda kəsilsə, `.kb_index.json` korlana bilər. **Tövsiyə:** əvvəl müvəqqəti fayla yazmaq, sonra `os.replace` etmək.
2. **Server Ollama-nı əvvəlcədən yoxlamır.** Bu, legacy koddur. Ollama sönülü olsa, DeepSeek çağırışları pulla edilir, sonra embedding uğursuz olur. P1-4 sayəsində heç bir fayl yazılmır, amma API xərci itir.
3. **`--local` chat modelinin (`qwen3:14b`) olub-olmadığını yoxlamır**, yalnız embedding modelini yoxlayır. Model yoxdursa, ilk generate çağırışında HTTP xətası çıxır və heç nə yazılmır.
4. **Fence qaydası sadələşdirilib.** Bağlayan fence açanla eyni 3 simvolla başlamalıdır. CommonMark-ın "bağlayan fence açandan qısa olmamalı və info string-i olmamalıdır" qaydası tətbiq olunmayıb. 4 backtick-li fence-lər ayrıca idarə olunmur. Real vault-da belə fence yoxdur (0 sətir).
5. **`CANDIDATE_THRESHOLD = 0.60` ölçülməyib.** Bu rəqəm hiss ilə seçilib, repo-da dəqiqlik benchmark-ı yoxdur.
6. **Prompt injection** (mətnə gizlədilmiş, modeli yönləndirən zərərli təlimat) **qarşısı alınmayıb.** Etibarsız mətn birbaşa LLM-ə gedir, nəticə diskə yazılır. P2-6 yalnız şəbəkə tərəfini bağlayır.
7. **`kb --merge` pipe ilə işləmir.** `stdin` pipe olanda "Merge into which note?" sualındakı `input()` `EOFError` verir. Bu, köhnə davranışdır.
8. **Bağlandı (2026-10-16): README-dəki "128K context" iddiası səhv idi.** Əvvəl yoxlamamışdım, çünki o, Nazirin orijinal mətni idi. DeepSeek-in qiymət səhifəsinə görə `deepseek-flash` DeepSeek-V4.1-Flash-dır: kontekst 1M token, maksimum çıxış 384K token. README düzəldildi. Chunking-in lazım olmadığı nəticəsi P2-2-dədir.
9. **launchd crash döngüsü.** 7448 dəfə `Address already in use` olub. Ehtimal olunan səbəb: server əl ilə işə salınanda launchd agent-i də işləyirdi. Agent yüklü olanda server-i əl ilə işə salmamaq lazımdır.
10. **Index sinxronlaşdırılan qovluqdadır** (Syncthing). Pipeline iki maşında eyni vaxtda işləsə, index-də konflikt yarana bilər.
11. **Model id dəyişə bilər** (P1-7). DeepSeek adları bir dəfə dəyişib. `/models`-i vaxtaşırı yoxlamaq faydalıdır.
12. **`kb` dayananda `--merge` təklif edir, amma `--merge` hədəfi adla yox, oxşarlıqla tapır** (P0-3). Eyni adlı qeydin oxşarlığı 0.60-dan aşağı olsa, o siyahıda görünməz. Onda `--merge` yeni qeyd yaratmağa keçər və eyni mesajla yenə dayanar. Qeyd itmir, amma ona birləşdirmək üçün CLI-da yol qalmır. **Mümkün həll:** `kb --merge --into <slug>`.

## Nazir üçün manual addımlar

1. **Server-i yeni kodla yenidən başladın** (P2-6, (a) variantı). Log rotation da burada edilir:
   ```bash
   mv ~/cke/server.log ~/cke/server.log.old        # və ya silin
   launchctl kickstart -k gui/$(id -u)/com.cke.server
   lsof -nP -iTCP:8000 -sTCP:LISTEN                # 127.0.0.1:8000 görünməlidir, *:8000 yox
   ```
   Log gələcəkdə yenə böyüsə, eyni iki əmri təkrarlayın: əvvəl `mv`, sonra `kickstart -k`.

   **2026-10-13:** server yenidən başladılıb və `127.0.0.1:8000`-də dinləyir. Amma bu, P0-3-dən əvvəl olub, işləyən proses isə kodu başlayanda yükləyir. P0-3 qorumasının server-də də işləməsi üçün `launchctl kickstart -k gui/$(id -u)/com.cke.server` əmrini bir dəfə də işlədin.
2. **`~/.zshrc`-də 122–123-cü sətirlərdəki köhnə `alias kb=...` sətirlərini özünüz silin.** 124-cü sətir (`alias kb="/Users/nazir/cke/kb"`) qalmalıdır.
3. **GitHub topics** (P3-3): repo səhifəsində ⚙ → Topics: `llm`, `rag`, `cybersecurity`, `obsidian`, `ollama`, `local-llm`, `knowledge-base`.
4. **Syncthing konflikt faylları:** `.obsidian/workspace.sync-conflict-20260707-...` və `...-20261006-...`. Toxunulmadı, saxlamaq və ya silmək sizin qərarınızdır.
5. **Push:** heç nə push edilməyib. Yoxlayıb özünüz edin: `git log --oneline origin/main..main`, sonra `git push`.
6. **Backup-lar:** hər şeyin düzgün olduğuna əmin olandan sonra `~/Desktop/CyberKB-prefix-20261012-2215.tar.gz` və `~/Desktop/kb_index-prefix.json` fayllarını silə və ya arxivə köçürə bilərsiniz.
