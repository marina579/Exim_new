# Quick Git Commands

## Initial Commit

```bash
cd /Users/sai/Documents/GitHub/Exim

# Add all files (respects .gitignore)
git add .

# Commit
git commit -m "Initial deployment-ready code"

# Add remote (if not already added)
git remote add origin <your-github-repo-url>

# Push to GitHub
git push -u origin main
```

## Verify what will be committed

```bash
# See what files will be added
git status

# See ignored files (should include .env, *.db, etc.)
git status --ignored
```

## Important Notes

- ✅ `.env.example` will be committed (template file)
- ❌ `.env` will NOT be committed (in .gitignore)
- ✅ All source code will be committed
- ❌ Database files, logs, cache will NOT be committed
