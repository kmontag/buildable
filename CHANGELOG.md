# CHANGELOG

## v0.2.0 (2024-08-16)

### Chore

* chore: formatting fixes ([`fc30c81`](https://github.com/kmontag/buildable/commit/fc30c810fc31e0ff78ede126d45a7261a69023b3))

* chore: add set-level validations and start standardized test layout ([`6d97d2c`](https://github.com/kmontag/buildable/commit/6d97d2cc3257deecd3c8d0c1e88581ecebc1791f))

### Documentation

* docs: update README and contributing guidelines ([`ad53151`](https://github.com/kmontag/buildable/commit/ad5315185230a253999879f4d890164f9231d055))

### Feature

* feat: add specific error for duplicate pointee IDs ([`77d3c93`](https://github.com/kmontag/buildable/commit/77d3c93e1ca76a6e93c981447951527b3fbe7d32))

* feat: add methods to move tracks ([`3ac8be1`](https://github.com/kmontag/buildable/commit/3ac8be1e2ca76122f4bf0a5ee605196f305fa122))

### Fix

* fix: disallow duplicate pointee IDs and fix SendsPre ID generation ([`e7ed501`](https://github.com/kmontag/buildable/commit/e7ed5014b4ec997954a071505d004572dc07706c))

## v0.1.1 (2024-08-16)

### Chore

* chore: remove unnecessary root semantic.yml configuration ([`720e9d2`](https://github.com/kmontag/buildable/commit/720e9d23bd2b828c4b2e793e73f696f727db5875))

* chore: don&#39;t increment major version from 0 automatically ([`8e13622`](https://github.com/kmontag/buildable/commit/8e13622ce6636d473c176f164b5d48eaaf28d707))

### Documentation

* docs: add how-to for PRs and local development ([`459cca4`](https://github.com/kmontag/buildable/commit/459cca405cd9c2495530a2f512ed7c79b6d2cfbc))

### Fix

* fix: remove non-existent quantization mapping on Transport ([`55af70c`](https://github.com/kmontag/buildable/commit/55af70c7cf8c1a46f9658a979d87a56f75ec0712))

## v0.1.0 (2024-08-16)

### Chore

* chore: fix tests on older python versions ([`18951a3`](https://github.com/kmontag/buildable/commit/18951a3301f5ef692b1d9ddb1dec7644610dbfda))

* chore: add .editorconfig ([`4efe486`](https://github.com/kmontag/buildable/commit/4efe4869b2c9f6f2a4590d83db76d2d28dd19a98))

* chore: style fixes ([`d682458`](https://github.com/kmontag/buildable/commit/d6824587d43286cd63b010afa21b637305777f58))

### Ci

* ci: add tests for python 3.8 ([`aeffbb9`](https://github.com/kmontag/buildable/commit/aeffbb90759d580b32b63140367dcfb47254b342))

### Feature

* feat: add key/MIDI mapping support for many high-level elements ([`7c733b4`](https://github.com/kmontag/buildable/commit/7c733b47e56652a3a4b6f51030d4ff492606985f))

### Fix

* fix: fix typing issues and set up semantic release ([`d20eca3`](https://github.com/kmontag/buildable/commit/d20eca341b2a184b2b160940d76f8e229a3788e6))

* fix: preserve misspelling in &#34;ViewStateSesstionTrackWidth&#34; tag

There are a number of misspellings in the Live set schema. We should
preserve them to keep our API as close as possible to the real XML document. ([`0679c31`](https://github.com/kmontag/buildable/commit/0679c31fac36c3e8df84e2db677a9874740d9806))

### Unknown

* add github workflows ([`52276a3`](https://github.com/kmontag/buildable/commit/52276a3d0af345976c3adb1354cc18a0eda3ad78))

* update README ([`9aba993`](https://github.com/kmontag/buildable/commit/9aba9937f48b0e4f3010c2a1f764331ebfb42bba))

* apply formatting auto-fixes ([`a09aa65`](https://github.com/kmontag/buildable/commit/a09aa657858eeb8b409e8fae7546ca57c0af03ad))

* initial implementation for copying tracks between sets ([`2a5e496`](https://github.com/kmontag/buildable/commit/2a5e4968665b8ca207361341e50598b283b1b362))

* initial package structure ([`fb66813`](https://github.com/kmontag/buildable/commit/fb66813823a93beb2b279809ea7f95cff1dd015f))
