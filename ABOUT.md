Redact; "To gather or organize works or ideas into a unified whole; to collect, order, or write in a written document or to put into a particular written form." (obsolete form).

### What

This is a utility program written to cover my own modest needs, but I hope that it can find some use for other ebook collectors (hi, fellow /r/datacurators!).  

The Epub Redactor is (for now) a Windows GUI tool for bulk-editing EPUB metadata, built for prepping books for Kobo e-readers; just load a folder of books into a table, select several at once, and apply the same field changes to all of them in one go. The UX is modeled on the program mp3tag.  It also borrows additional functionality from Calibre, if you have that installed.

### Why

The challenge with curating epub files, is that most available utilities are outdated and only made for editing file-by-file, which is tiresome once you have an entire series of books on your hands. The only complete tool on the market is [Calibre](https://calibre-ebook.com/), which forces you to import all books into its internal database for processing, instead of editing your files in your existing folder locations. 

The Epub Redactor handles this in a cheeky way; for a lot of the more advanced functionality, it requires Calibre to be installed and configured on your local machine, and simply uses that for background functionality. So you get access to Calibre format conversion and metadata scraping, but in a more practical UX.

If you find the interface familiar, you are probably already familiar with the magnificent program [MP3Tag by Florian Heidenreich](https://www.mp3tag.de/en/), which does for mp3 files what I want this to do for epub files.  If you use mp3tag, I strongly suggest that you donate a small amount for its use, especially if you are borrowing the UX layout like I did. 

### How

This program is coded using Claude AI. You might hate AI, but in the hands of any reasonably competent programmer, it is a great tool. The time spent on writing code is now actually spent on QA, testing functionality and edge cases. The concept which I fed into Claude is mine, and has been mine for over 10 years; I have just never trusted AI coding to be of high enough quality to do it before now.

I've included the program code, the changelogs, and just about everything except the prompts, but if you are very curious, those too can be provided for further examination. 
If you feel like getting your pitchfork ready, just don't use it. It's that simple. On the other side of the coin, small changes are very quick to implement if there is something that would improve your workflow. 

Pubocyno, August 2026
