@echo off
REM Llançador de l'app Seguiment de Preus.
REM Fa servir el Python portàtil de la carpeta python_embed, no cal tenir
REM Python instal·lat al sistema.

cd /d "%~dp0"
python_embed\python.exe -m streamlit run app.py

pause