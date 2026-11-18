RESIZER | Windows 64-bit

**[Pobierz Resizer.exe](https://github.com/MichalPisanczuk/PhotoResizer/releases/latest/download/Resizer.exe)** (Windows 64-bit, bez instalacji) · [wszystkie wersje](https://github.com/MichalPisanczuk/PhotoResizer/releases)

1. Wypakuj Resizer.exe do wybranego folderu i uruchom go.
   Aplikacja działa lokalnie i nie wymaga instalacji Pythona.
2. Kliknij „Dodaj zdjęcia…” i zaznacz wiele plików.
3. Wybierz tryb, format wyjściowy i folder zapisu.
4. Kliknij „Optymalizuj”. Tabela pokaże wagę każdego zapisanego pliku i jego wymiary.
   Zaznacz wiersz, aby zobaczyć ścieżkę wyniku lub powód pominięcia.

BEZSTRATNY
Zachowuje piksele i rozdzielczość. WebP jest domyślnym formatem, a PNG
przydaje się między innymi do obrazów o większej głębi kolorów. Wybór JPG
kopiuje źródłowe pliki JPG bajt w bajt. Zapis innych formatów do JPG jest
dostępny w trybie WWW. Bezstratny wynik może ważyć tyle samo lub więcej,
zwłaszcza po zmianie formatu.

WWW
JPG i WebP mają regulowaną jakość, domyślnie 92. Opcja zmiany wymiarów
skaluje duże zdjęcia proporcjonalnie do co najmniej 1920 × 1080 px w poziomie
lub 1080 × 1920 px w pionie. Jeśli którykolwiek bok już jest poniżej swojego
minimum, program zostawi wymiary źródłowe. Zapis do JPG stosuje białe tło
w miejscach przezroczystych. Wybierz WebP lub PNG, by zachować przezroczystość.

PLIKI
Przykładowe formaty wejściowe to JPG, PNG, WebP, BMP, TIFF i GIF. Program
obsługuje obrazy statyczne. Animacje i dokumenty wielostronicowe są pomijane.
Oryginały pozostają na swoim miejscu. Wyniki otrzymują końcówkę „_optymalizacja”
i w razie potrzeby kolejny numer. Przy ponownym zapisie obrazów program może
usunąć metadane aparatu. Orientacja i obsługiwane profile kolorów są zachowywane.

KOD ŹRÓDŁOWY
Zależności do uruchomienia z kodu: Python z Tkinter oraz Pillow 11.2.1 lub nowszy.
Uruchomienie: python resizer.py
Budowa z zainstalowanym PyInstaller: python -m PyInstaller --onefile --windowed --name Resizer resizer.py
