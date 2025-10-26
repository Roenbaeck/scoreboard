# Security Guidelines

## Current Security Features

### ✅ Implemented
1. **Password Hashing**: pbkdf2:sha256 via werkzeug
2. **Session-Based Auth**: No tokens in URLs, httponly cookies
3. **User Data Isolation**: Per-user data directories
4. **Input Validation**: Username sanitization (alphanumeric + hyphens)
5. **Rate Limiting**: 5 failed login attempts per IP within 5 minutes → 429 response
6. **Upload Size Limits**: 5MB max request size
7. **Random Session Secrets**: Auto-generated if not provided via env var

### ⚠️ Recommendations for Production

#### Critical
1. **Set Session Secret Key**:
   ```bash
   export SCOREBOARD_FLASK_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
   ```
   Add to your shell profile or systemd service file.

2. **Use HTTPS** (Required for production):
   - Deploy behind nginx/Apache with SSL certificate
   - Use Let's Encrypt for free SSL certificates
   - Configure reverse proxy to handle HTTPS termination

3. **Change Default Port**:
   - Don't expose port 8081 directly to internet
   - Use reverse proxy (nginx/Apache) on ports 80/443

#### Important
4. **Firewall Configuration**:
   ```bash
   # Allow only from specific IPs or local network
   sudo ufw allow from 192.168.1.0/24 to any port 8081
   ```

5. **Strong Passwords**:
   - Minimum 12 characters recommended
   - Use `generate_password.py` to create hashes
   - Never commit `users.json` to git (already in .gitignore)

6. **Run as Non-Root User**:
   ```bash
   # Create dedicated user
   sudo useradd -r -s /bin/false scoreboard
   sudo chown -R scoreboard:scoreboard /path/to/scoreboard
   ```

7. **Enable CSRF Protection**:
   ```bash
   pip install flask-wtf
   ```
   Then add CSRF tokens to all forms (future enhancement).

#### Optional Enhancements
8. **Additional Rate Limiting**:
   - Consider `flask-limiter` for per-endpoint limits
   - Limit scraper starts per user per hour
   - Limit stats generation calls

9. **Logging & Monitoring**:
   - Log all login attempts (success/failure)
   - Monitor for unusual activity patterns
   - Set up alerts for repeated 429 responses

10. **Content Security Policy**:
    - Add CSP headers to prevent XSS
    - Restrict script sources to 'self'

11. **Session Timeout**:
    ```python
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
    ```

12. **IP Whitelist** (if needed):
    - Restrict access to known IP ranges
    - Use nginx/Apache geo-blocking

## Known Limitations

### Public Overlay
- `/<username>/overlay/` is intentionally public (no auth)
- Designed for OBS/vMix embedding
- Can be DoS'd if URL is public
- **Mitigation**: Keep URLs secret, use nginx rate limiting

### No CSRF Protection
- POST endpoints lack CSRF tokens
- Only protects against cross-site attacks
- Session auth provides some protection
- **Mitigation**: Add flask-wtf for production

### XML Upload Token
- Token in `users.json` is static
- Rotate periodically if exposed
- Consider time-based tokens for production

## Deployment Checklist

- [ ] Set `SCOREBOARD_FLASK_SECRET` environment variable
- [ ] Use HTTPS (reverse proxy with SSL)
- [ ] Run as non-root user
- [ ] Configure firewall rules
- [ ] Change all default passwords
- [ ] Restrict network access (local only or VPN)
- [ ] Enable system logging
- [ ] Set up automated backups of `users.json` and `data/`
- [ ] Document recovery procedures
- [ ] Test rate limiting (try 6 failed logins)

## Example Nginx Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name scoreboard.example.com;

    ssl_certificate /etc/letsencrypt/live/scoreboard.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/scoreboard.example.com/privkey.pem;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    
    location /login {
        limit_req zone=login burst=3 nodelay;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }
}
```

## Security Contacts

If you discover a security vulnerability:
1. Do not open a public GitHub issue
2. Contact the repository owner privately
3. Provide detailed reproduction steps
