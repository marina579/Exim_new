# Git Authentication Setup Guide

## Quick Setup Options

### Option 1: Personal Access Token (Recommended for HTTPS)

1. **Generate a Personal Access Token on GitHub:**
   - Go to: https://github.com/settings/tokens
   - Click "Generate new token" → "Generate new token (classic)"
   - Name: "Exim Deployment"
   - Expiration: Set your preference (90 days, 1 year, or no expiration)
   - Scopes: Select `repo` (full control of private repositories)
   - Click "Generate token"
   - **COPY THE TOKEN** (you won't see it again!)

2. **Use Token for Authentication:**
   ```bash
   cd /Users/sai/Documents/GitHub/Exim
   
   # When prompted for password, use the token instead
   git push origin main
   
   # Username: marina579
   # Password: <paste your token here>
   ```

3. **Or configure Git to use token:**
   ```bash
   git remote set-url origin https://marina579:YOUR_TOKEN@github.com/marina579/Exim.git
   ```

### Option 2: SSH Key (Recommended for Frequent Use)

1. **Check if you have SSH keys:**
   ```bash
   ls -la ~/.ssh/id_*.pub
   ```

2. **Generate SSH key (if you don't have one):**
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   # Press Enter to accept default location
   # Enter a passphrase (optional but recommended)
   ```

3. **Add SSH key to GitHub:**
   ```bash
   # Copy your public key
   cat ~/.ssh/id_ed25519.pub
   # Or on macOS:
   pbcopy < ~/.ssh/id_ed25519.pub
   ```
   
   - Go to: https://github.com/settings/keys
   - Click "New SSH key"
   - Title: "MacBook Air" (or any name)
   - Paste your public key
   - Click "Add SSH key"

4. **Update remote URL to use SSH:**
   ```bash
   cd /Users/sai/Documents/GitHub/Exim
   git remote set-url origin git@github.com:marina579/Exim.git
   ```

5. **Test SSH connection:**
   ```bash
   ssh -T git@github.com
   # Should say: "Hi marina579! You've successfully authenticated..."
   ```

### Option 3: GitHub CLI (gh) - Easiest

1. **Install GitHub CLI (if not installed):**
   ```bash
   brew install gh
   ```

2. **Authenticate:**
   ```bash
   gh auth login
   # Follow the prompts:
   # - Choose GitHub.com
   # - Choose HTTPS or SSH
   # - Authenticate in browser
   ```

## Configure Git User (If Not Set)

```bash
# Set your name
git config --global user.name "Your Name"

# Set your email (use GitHub email)
git config --global user.email "your_email@example.com"
```

## Verify Setup

```bash
# Check remote URL
git remote -v

# Check user config
git config --global user.name
git config --global user.email

# Test connection (for SSH)
ssh -T git@github.com

# Or test push
git push origin main
```

## Troubleshooting

### If you get "Authentication failed":
- For HTTPS: Make sure you're using a Personal Access Token, not your GitHub password
- For SSH: Make sure SSH key is added to GitHub

### If you get "Permission denied":
- Check that your GitHub username matches
- Verify you have write access to the repository
- For organizations, make sure you have the right permissions

### If you get "Repository not found":
- Check repository name: `marina579/Exim`
- Verify the repository exists and you have access
- Check if it's a private repository (you need proper authentication)

## Quick Commands Reference

```bash
# View current remote
git remote -v

# Change remote URL to HTTPS
git remote set-url origin https://github.com/marina579/Exim.git

# Change remote URL to SSH
git remote set-url origin git@github.com:marina579/Exim.git

# Push to GitHub
git push origin main

# Push and set upstream
git push -u origin main
```

