# Config Directory — Secrets & Environment Guidance

## NEVER store real credentials here

The `config/install/dcpas_chatbot.settings.yml` file sets default values that
are imported when the module is first installed. It is committed to version
control. **Do not put real API keys, tokens, or secrets into this file.**

The `openai_api_key` field ships as an empty string (`''`) and must stay that way.

---

## Secret injection — recommended approaches

### 1. Environment variable (preferred for FedRAMP production)

Set `DCPAS_OPENAI_API_KEY` on the server. The module reads this in preference
to anything stored in Drupal config:

```bash
export DCPAS_OPENAI_API_KEY="your-key-here"
```

For systemd-based Drupal hosts:
```ini
# /etc/systemd/system/php-fpm.service.d/dcpas.conf
[Service]
Environment=DCPAS_OPENAI_API_KEY=your-key-here
```

For Azure-hosted Drupal (App Service):
```
Application Settings → DCPAS_OPENAI_API_KEY = <key from Key Vault reference>
```

### 2. Drupal settings.php injection

Override the config value in `settings.php` without committing it:

```php
// web/sites/default/settings.php (or settings.local.php — never committed)
$config['dcpas_chatbot.settings']['openai_api_key'] = getenv('DCPAS_OPENAI_API_KEY')
  ?: 'fallback-key-if-env-not-set';
```

### 3. Azure Key Vault (FedRAMP production path)

For deployments requiring FedRAMP compliance:

1. Store the API key in Azure Key Vault as a secret.
2. Grant the Drupal app service identity `Key Vault Secrets User` role.
3. Reference the secret via an App Service Key Vault reference:
   ```
   @Microsoft.KeyVault(SecretUri=https://your-vault.vault.azure.net/secrets/dcpas-openai-key/)
   ```
4. Map the reference to the `DCPAS_OPENAI_API_KEY` environment variable.
5. The module will pick it up automatically via `getenv()`.

---

## Config export warnings

When you export Drupal config (`drush cex`), the `dcpas_chatbot.settings.yml`
in `config/sync/` will contain the **current** config values from the database —
including any API key stored there. Before committing config exports:

1. Blank out the `openai_api_key` field in the exported file.
2. Run the pre-commit hook (`make install-hooks`) which will catch non-empty key patterns.

---

## Env var precedence (summary)

| Source | Priority | Notes |
|--------|----------|-------|
| `DCPAS_OPENAI_API_KEY` env var | **Highest** | Set on server; never in code |
| `settings.php` `$config` override | High | In non-committed local settings |
| Drupal config (`openai_api_key`) | Lowest | For demo/dev only; blank in production |
