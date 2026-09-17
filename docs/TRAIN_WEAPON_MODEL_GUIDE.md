# Project Garuda — Weapon & Threat Model Training Guide

This guide walks you through training/fine-tuning Project Garuda's threat detector (`threat_yolov8n.pt`) in Google Colab using a **free Cloud GPU** in ~10 minutes, with **zero load on your local PC**.

---

## 1. Quick Steps to Train on Google Colab

1. **Open Google Colab**:
   Go to [https://colab.research.google.com/](https://colab.research.google.com/)
2. **Upload the Notebook**:
   - Click **File > Upload notebook**
   - Select [`training/train_threat_model_colab.ipynb`](file:///c:/Users/SOUMYA.B/Documents/project%20files/project%20garuda/training/train_threat_model_colab.ipynb) from your Project Garuda directory.
3. **Ensure GPU is Enabled**:
   - Click **Runtime > Change runtime type**
   - Select **T4 GPU** (Free) and click **Save**.
4. **Run All Cells**:
   - Click **Runtime > Run all** (or press `Ctrl + F9`).
5. **Download Model**:
   - In ~10 minutes, the training completes, and Google Colab will automatically trigger a browser download for **`threat_yolov8n.pt`** (~6 MB).

---

## 2. Deploying the Model into Project Garuda

1. Copy the downloaded `threat_yolov8n.pt` file.
2. Paste and replace:
   ```
   c:\Users\SOUMYA.B\Documents\project files\project garuda\ai_engine\models\threat_yolov8n.pt
   ```
3. Restart or reload the backend:
   Project Garuda's `WeaponDetector` in `ai_engine/detection/weapon_detector.py` automatically detects and loads the new weights on the next frame with zero configuration changes required!

---

## 3. Threat Model Architecture & Classes

| Class ID | Class Label | Type | UI Icon | Presentation Status |
| :--- | :--- | :--- | :--- | :--- |
| **0** | **Gun** | Firearm (Pistol, Rifle, Handgun) | 🔫 | Active in Streamlined HUD |
| **1** | **explosion** | Explosives & Flash | 💣 | Filtered in Presentation |
| **2** | **grenade** | Hand Grenades | 💣 | Filtered in Presentation |
| **3** | **knife** | Bladed Weapons (Knives, Daggers) | 🗡️ | Active in Streamlined HUD |

Project Garuda incorporates **Negative Mutual Exclusion** in `ai_engine/detection/weapon_detector.py`:
- Smartphones, wallets, and vehicle license plates are cross-referenced with YOLOv8 COCO classes (`cell phone`, `car`) and suppressed to maintain a **near-zero false alarm rate**.
