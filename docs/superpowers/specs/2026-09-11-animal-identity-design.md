# Animal identity

2026-09-11

The farm's own register number becomes the animal's identity in the system:
`A039/26` for a heifer, `B013/26` for a bull. Allocated by the system, read-only
where it is shown, editable only through a form that will not let you invent a
number that is taken or a year that has not happened.

This is the first of five pieces. The others — calving routing, the backdating
ladder, herd membership as of a date, and the React Animals page — are named at
the end and specified separately.

## Why now

The farm says "A039/26" out loud. The system says `NIKKI-211584`. Every
conversation between the two needs a translation nobody wrote down, and 92 of
366 animals have no register number at all.

## What already exists

`demo/place_herd_inventory.py` loaded the 26 August inventory: it maps herd
names between the sheet and the site, tidies two transcription habits out of the
book numbers, and writes the result to `Animal.book_number`. It deliberately
creates no animals and deliberately does not name records from the book number.

`tests/test_book_numbers.py` asserts that last decision, with its reason: four
sheet entries are not register numbers, some animals have none, and "a naming
scheme that cannot name every record is not a naming scheme."

That objection is correct and this design answers it rather than ignoring it.
Every record that cannot get a number from the register is **allocated** one from
the free gaps in its birth year, so the scheme does name every record.

## The grammar

    <prefix><seq>/<yy>        A039/26   B013/26

| Part | Rule |
|---|---|
| `prefix` | `A` female, `B` male. Derived from sex. Never typed. |
| `seq` | Three digits, zero-padded, 1–999. |
| `yy` | Two digits, the **year of birth**. `26` is 2026. |

Sequences are independent per prefix per year: the inventory runs `B013/26`
through `B024/26` alongside `A002/26` through `A039/26`.

## Decisions

| Question | Decision |
|---|---|
| Where the ID lives | `Animal.tag_number`, which is the autoname field, so the ID *is* the record name. |
| What `book_number` becomes | The register's own words, preserved as evidence — including the four entries that are not register numbers. It is not the authority and is not kept in sync. |
| Allocation at birth | `max(seq) + 1` for that prefix and year. Gaps are offered, never taken silently. |
| Collision safety | The ID is the primary key. A duplicate is refused by the database; the allocator re-reads and retries. No counter table to drift. |
| Who may renumber | Anyone with write permission on Animal — today, System Manager and Livestock Manager only. |
| The 92 with no register number | Allocated from the free gaps in their birth year. |
| The 57 active animals absent from the 9 Sep inventory | Renamed like the rest, and listed in the report. Nothing is retired by a script. |

## Architecture

### `serverscripts/common/animal_id.py`

The only module that knows what an animal ID is.

```
prefix_for_sex(sex)              -> "A" | "B"
parse(animal_id)                 -> {prefix, seq, yy, year} | None
format_id(prefix, seq, yy)       -> "A039/26"
tidy(raw)                        -> a register entry with its two transcription
                                    habits corrected, or the raw text unchanged
                                    when it is not a register number at all
taken(prefix, yy)                -> {int, ...} sequences already used
next_free(prefix, yy)            -> int
gaps(prefix, yy, limit)          -> [int, ...] free numbers below the high-water mark
allocate(sex, birth_date)        -> "A040/26"
assert_assignable(id, sex, cur)  -> throws, naming the gaps, when it cannot be used
```

`tidy` moves here from `place_herd_inventory._clean_book`, which imports it back
under the old name so there is one implementation. It gains the `B` prefix and
keeps its refusal to guess: `ELLA` and `23:29` come back exactly as found.

`taken` reads `Animal.name`. The register mirror is not consulted — an authority
and a copy that disagree is worse than no copy.

### Endpoints — `serverscripts/animals/`

```
suggest_animal_id(sex, birth_date)   -> {id, year, gaps, high_water}
rename_animal({animal, new_id})      -> {ok, name, renamed_from}
```

`suggest_animal_id` is read-guarded. `rename_animal` requires write permission on
Animal, and runs `assert_assignable` before `frappe.rename_doc`. All twelve Link
fields that point at Animal are standard DocFields, so the rename repoints them.

### Birth

`common/animal.create_calf` allocates when the caller passes no tag, instead of
throwing "Calf tag number is required." The desk and mobile birth forms show the
allocated ID read-only beside the calf's sex; changing the sex reallocates it.

### The register load — `demo/load_herd_register.py`

Idempotent, dry-run by default, run by hand. Not a patch: a patch that renames
animals would fire on every site it ever reached, including the live one.

    bench --site <site> execute upande_livestock.demo.load_herd_register.run
    bench --site <site> execute upande_livestock.demo.load_herd_register.run --kwargs "{'apply': True}"

It reads the two workbooks in `references/` directly, and in one pass:

1. Reserves every ID the sheet claims, so allocation cannot hand out a number
   the sheet is about to use.
2. Creates `Lactation Group 3 TEST HERD` and maps the sheet's groups onto the
   site's herd names.
3. Matches the 273 animals the register already identifies; corrects herd, name
   and date of birth; renames each record to its register number.
4. Creates the 40 animals the farm has and the system does not.
5. Allocates IDs from birth-year gaps for the 92 with no register number, and
   for the six whose register entry is broken, and renames them.
6. Recomputes every herd's headcount.
7. Reports: what moved, what was created, every allocated number and why, and
   the 57 active animals the 9 Sep inventory does not list.

## Testing

- `tests/test_animal_id.py` — the grammar; `tidy` on both prefixes and on text
  that is not an ID; per-prefix-per-year independence; `gaps` finding holes below
  the high-water mark; `assert_assignable` refusing a future year, a taken
  number and a prefix that contradicts sex.
- `tests/test_book_numbers.py` — the assertion that the ID is not the record name
  is **inverted**, and its docstring says why the earlier reasoning no longer
  holds.
- `tests/test_calf_birth.py` — a calf booked with no tag is allocated one that
  matches its sex and birth year.

## Out of scope

Calving routing, the backdating ladder, herd membership as of a date, and the
React Animals page. Each is its own spec.

## Risks

**The rename is one-way in practice.** 366 `rename_doc` calls rewrite twelve
link fields across a dozen doctypes. It is run dry first, and the report is read
before `apply: True`.

**Allocated numbers are not the farm's numbers.** 92 animals get an ID the
register never gave them. The report names every one, so the farm can correct any
that clash with a paper record.
