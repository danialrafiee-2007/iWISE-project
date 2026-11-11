TRUTH GUARDIAN: READY-MADE PACKAGE
Hallucination detection for RAG and agent answers. iWISE 2026, AI Challenge 4. Build {build}.

TO RUN IT
  Downloaded with Get-Truth-Guardian.bat: it has done everything and opened the app. Later, double-click the
  Truth Guardian shortcut on the desktop (if you asked for one) or TruthGuardian.bat in the TruthGuardian folder.

  Received as a copied folder:
    1. Copy this whole folder to your computer.
    2. Double-click Start-Truth-Guardian.bat.
    3. The app opens in your browser.

  If Windows says it protected your PC, choose More info, then Run anyway.
  To stop the app, close its black window.

HOW LONG IT TAKES
  The first start unpacks the app once: about 5 minutes until the page opens and 6 until the models are ready.
  Later starts: about 1 minute until the page opens and 2 until the models are ready. Measured on a 4-core laptop.
  The page shows when the models are ready.

WHAT IT NEEDS
  64-bit Windows 10 (version 1803 or newer) or Windows 11, about {need_gb} GB of free disk space and 8 GB of memory.
  No internet, and nothing is installed in Windows. Everything stays in one folder; delete that folder (and the
  desktop shortcut, if you made one) to remove it all.

IF SOMETHING GOES WRONG
  "Port 8765 is used by another program": open a command window in the TruthGuardian folder and run
  TruthGuardian.bat --port 8780
  "A package part could not be unpacked": check the free space, copy the packages folder again and start again; it
  continues where it stopped.
  "... is missing from the packages folder": run Get-Truth-Guardian.bat in this folder; it downloads what is missing.
  To check the copy, compare packages\SHA256SUMS.txt with:  certutil -hashfile packages\truth-guardian-1-of-N.zip SHA256
  TruthGuardian.bat check, in the TruthGuardian folder, lists what is present and what is missing.

GOOD TO KNOW
  Get-Truth-Guardian.bat in this folder starts the app too. Without internet it starts the copy already here; with
  internet it also gets a newer version, if there is one.
  If the downloaded parts were deleted after unpacking, the TruthGuardian folder still holds the whole app: to move the
  project to another computer, copy that folder and double-click TruthGuardian.bat in it.


راهنمای فارسی

اجرا
  اگر با Get-Truth-Guardian.bat دانلود کرده‌اید، همه‌ی کارها انجام شده و برنامه باز شده است. دفعه‌های بعد روی میانبر
  Truth Guardian روی دسکتاپ (اگر ساخته‌اید) یا روی TruthGuardian.bat در پوشه‌ی TruthGuardian دوبار کلیک کنید.

  اگر این پوشه را کپی‌شده دریافت کرده‌اید:
    ۱. تمام این پوشه را روی کامپیوتر خود کپی کنید.
    ۲. روی Start-Truth-Guardian.bat دوبار کلیک کنید.
    ۳. برنامه در مرورگر باز می‌شود.

  اگر ویندوز پیام داد که از کامپیوتر محافظت کرده است، More info و بعد Run anyway را بزنید.
  برای بستن برنامه، پنجره‌ی سیاه آن را ببندید.
  پیام‌های پنجره‌ی سیاه انگلیسی است، چون پنجره‌ی فرمان ویندوز ۱۰ حروف فارسی را به صورت مربع خالی نشان می‌دهد.

زمان
  اجرای اول برنامه یک بار از حالت فشرده باز می‌شود: حدود ۵ دقیقه تا باز شدن صفحه و ۶ دقیقه تا آماده شدن مدل‌ها.
  اجراهای بعدی: حدود ۱ دقیقه تا باز شدن صفحه و ۲ دقیقه تا آماده شدن مدل‌ها. این زمان‌ها روی یک لپ‌تاپ ۴ هسته‌ای اندازه‌گیری شده‌اند.
  آماده شدن مدل‌ها در خود صفحه نشان داده می‌شود.

نیازمندی‌ها
  ویندوز ۱۰ نسخه‌ی ۱۸۰۳ یا جدیدتر یا ویندوز ۱۱ (۶۴ بیتی)، حدود {need_gb} گیگابایت فضای خالی و ۸ گیگابایت حافظه.
  اینترنت لازم نیست و چیزی در ویندوز نصب نمی‌شود. همه‌چیز در یک پوشه می‌ماند و با پاک کردن آن پوشه (و میانبر دسکتاپ،
  اگر ساخته‌اید) کاملاً حذف می‌شود.

اگر مشکلی پیش آمد
  پیام «Port 8765 is used by another program»: در پوشه‌ی TruthGuardian یک پنجره‌ی فرمان باز کنید و این را اجرا کنید:
  TruthGuardian.bat --port 8780
  پیام «A package part could not be unpacked»: فضای خالی را بررسی کنید، پوشه‌ی packages را دوباره کپی کنید و دوباره اجرا کنید؛ از همان‌جا ادامه می‌دهد.
  پیام «is missing from the packages folder»: فایل Get-Truth-Guardian.bat را در همین پوشه اجرا کنید؛ آنچه کم است را دانلود می‌کند.
  فرمان TruthGuardian.bat check در پوشه‌ی TruthGuardian نشان می‌دهد چه چیزی هست و چه چیزی نیست.

خوب است بدانید
  فایل Get-Truth-Guardian.bat در همین پوشه هم برنامه را اجرا می‌کند. بدون اینترنت همان نسخه‌ی موجود را اجرا می‌کند و با
  اینترنت اگر نسخه‌ی تازه‌تری باشد آن را هم می‌گیرد.
  اگر بعد از باز شدن بسته، فایل‌های دانلودشده پاک شده باشند، پوشه‌ی TruthGuardian همچنان کل برنامه را دارد: برای بردن
  پروژه به کامپیوتر دیگر، همان پوشه را کپی کنید و روی TruthGuardian.bat داخل آن دوبار کلیک کنید.
