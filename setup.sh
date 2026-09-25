#!/bin/bash
set -e

DOMAIN="alaminhosting.com"
EMAIL="mdalaminmmmnnn037@gmail.com"
ADMIN_EMAIL="mdalaminmmmnnn037@gmail.com"
ADMIN_PASSWORD="ALAMIN@DD"
APP_DIR="/opt/alaminhosting"

echo "🚀 ALAMIN HOSTING Setup..."
echo "================================"

echo "[1/7] System update..."
sudo apt update -y

echo "[2/7] Installing packages..."
sudo apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx ufw

echo "[3/7] Creating directories..."
sudo mkdir -p $APP_DIR/templates
sudo mkdir -p $APP_DIR/bots

echo "[4/7] Setting up Python venv..."
sudo python3 -m venv $APP_DIR/venv
sudo $APP_DIR/venv/bin/pip install --upgrade pip
sudo $APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt

echo "[5/7] Configuring Nginx..."
sudo cp $APP_DIR/nginx.conf /etc/nginx/sites-available/alaminhosting
sudo ln -sf /etc/nginx/sites-available/alaminhosting /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "[6/7] Configuring systemd..."
sudo cp $APP_DIR/alaminhosting.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alaminhosting
sudo systemctl start alaminhosting

echo "[7/7] Firewall..."
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

echo ""
echo "================================"
echo "✅ Setup Complete!"
echo "================================"
echo ""
echo "🌐 Admin: https://$DOMAIN/login"
echo "📧 Email: $ADMIN_EMAIL"
echo "🔑 Password: $ADMIN_PASSWORD"
echo ""
echo "📝 SSL Setup (optional):"
echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo ""