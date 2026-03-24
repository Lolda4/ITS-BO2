# Přístupové údaje a IP adresy k ITS-BO serveru

Zde jsou uloženy klíčové IP adresy a porty pro přístup na testovací server, jak z lokální sítě v laboratoři, tak z vnější mobilní sítě při testování venku.

## 1. Laboratorní přístup (Lokální síť)
Pro připojení na server přímo ze sítě laboratoře.

- **SSH Přístup:**  
  `ssh itsbo@192.168.0.161`

## 2. Terénní přístup (Z venkovní mobilní sítě / Internetu)
Tyto adresy a porty budete muset zadat do nastavení mobilní OBU aplikace s telefonem venku pro testování.

- **SSH Přístup:**  
  `ssh itsbo@147.32.102.209`

- **Backend API (REST):**  
  `http://147.32.102.209:8000`

- **UDP Control Loop (pro navazování spojení):**  
  `147.32.102.209:4567`

- **BurstReceiver (příjem hlavních telemetrických dat):**  
  `147.32.102.209:5100`

---
*Tip pro OBU aplikaci:*
V nastavení OBU aplikace ve vašem OnePlus 8 zadejte pro venkovní testování IP `147.32.102.209` a API port `8000`. Ostatní UDP porty by si měla aplikace odvodit, případně se nastavují přímo v kódu dle smlouvy.
