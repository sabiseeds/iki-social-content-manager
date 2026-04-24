#!/bin/bash
# ── Content Manager VPS Setup Script ──────────────────────────────────────────
# Run this ONCE on the VPS after copying the app files.
# Usage: bash /opt/content-manager/setup_vps.sh
# ──────────────────────────────────────────────────────────────────────────────
set -e

APP_DIR="/opt/content-manager"
DOMAIN="iki-social.ggcvietnam.com.vn"
SERVICE_USER="$USER"

echo "==> [1/7] Updating system packages..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

echo "==> [2/7] Creating Python venv and installing dependencies..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install notebooklm-py

echo "==> [3/7] Writing systemd service..."
sudo tee /etc/systemd/system/content-manager.service > /dev/null <<EOF
[Unit]
Description=Content Manager (NotebookLM Webapp)
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn server:app --host 127.0.0.1 --port 7860
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "==> [4/7] Writing Nginx config..."
sudo tee /etc/nginx/sites-available/content-manager > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass         http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        client_max_body_size 25M;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/content-manager /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

echo "==> [5/7] Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable content-manager
sudo systemctl start content-manager

echo "==> [6/7] Obtaining SSL certificate via Certbot..."
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@ggcvietnam.vn --redirect

echo "==> [7/7] Final service status..."
sudo systemctl status content-manager --no-pager

echo ""
echo "✅ Deployment complete! App is live at https://$DOMAIN"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status content-manager   # check status"
echo "  sudo journalctl -u content-manager -f   # follow logs"
echo "  sudo systemctl restart content-manager  # restart"
