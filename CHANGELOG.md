# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2025-10-26

### Added
- **Multi-user support** with path-based routing (`/<username>/control`, `/<username>/overlay/`, etc.)
- **Session-based authentication** using username + password instead of single shared token
- **User management system** via `users.json` configuration file
- **Per-user data isolation** in `data/<username>/` directories
- **Rate limiting** on login endpoint (5 failed attempts per IP per 5 minutes)
- **Brute force protection** with IP-based attempt tracking
- **Automatic session secret generation** when `SCOREBOARD_FLASK_SECRET` not set
- **Upload size limits** (5MB maximum request size)
- **Password hashing** using pbkdf2:sha256 via werkzeug
- **Per-user scraper instances** - multiple users can run independent scrapers simultaneously
- **Per-user token validation** for scoreboard.xml uploads
- `generate_password.py` utility for creating password hashes
- `users.json.example` template file
- `SECURITY.md` with comprehensive security guidelines and deployment checklist
- Enhanced README.md with multi-user setup instructions

### Changed
- **BREAKING**: Replaced single `PAGE_PASSWORD` environment variable with `users.json` config file
- **BREAKING**: All authenticated endpoints now require session-based login
- **BREAKING**: All URLs now use `/<username>/` prefix (e.g., `/lars/control`, `/lars/overlay/`)
- **BREAKING**: Scoreboard XML files moved from root `scoreboard.xml` to `data/<username>/scoreboard.xml`
- **BREAKING**: Scraper logs moved from root `scraper.log` to `data/<username>/scraper.log`
- **BREAKING**: Generated stats now saved to `data/<username>/stats_*.html`
- Server now generates random session secret on startup if not configured (with warning)
- Control panel UI updated to extract username from URL path
- Scoreboard.js updated to use username-specific paths and localStorage keys
- Token now injected into scoreboard.html via server-side template rendering

### Security
- Passwords stored as pbkdf2:sha256 hashes instead of plaintext
- Session cookies used instead of URL-based tokens
- Rate limiting prevents brute force login attacks
- User data completely isolated in separate directories
- Added `.gitignore` entries for `users.json`, `data/`, and Python cache files

### Migration Guide from v1.2.8

1. **Create users.json**:
   ```bash
   cp users.json.example users.json
   python3 generate_password.py your_password
   # Edit users.json with the generated hash
   ```

2. **Move data files**:
   ```bash
   mkdir -p data/your_username
   mv scoreboard.xml data/your_username/ 2>/dev/null || true
   mv scraper.log data/your_username/ 2>/dev/null || true
   ```

3. **Update URLs**:
   - Old: `http://localhost:8081/control`
   - New: `http://localhost:8081/login` (then navigate to `/your_username/control`)
   - Old overlay: `http://localhost:8081/overlay/`
   - New overlay: `http://localhost:8081/your_username/overlay/`

4. **Update OBS/vMix sources** with new overlay URL including username

5. **Remove old configuration**:
   - Delete `PAGE_PASSWORD` environment variable
   - No longer need to set tokens in JavaScript files

## [1.2.8] - 2025-10-XX

Last single-user release. Stable and simpler for single-user deployments.

### Features
- Single-user scoreboard with manual score control
- Profixio match scraper integration
- Automatic stats generation from match data
- OBS/vMix overlay support
- Undo/redo functionality
- Customizable team names and colors
- Token-based upload authentication
- Simple setup with single `PAGE_PASSWORD`

### Components
- `server.py` - Single-user Flask server
- `scraper.py` - Profixio match data scraper
- `stats.py` - Player statistics generator
- `html/scoreboard.html` - Manual controller interface
- `html/index.html` - Streaming overlay
- `html/scoreboard.js` - Controller logic with undo/redo

---

## Version Notes

- **v2.0.0**: Major rewrite for multi-user support. Not backward compatible with v1.2.8 without migration.
- **v1.2.8**: Stable single-user version. Use this if you don't need multi-user features.

For security considerations when deploying to production, see [SECURITY.md](SECURITY.md).
