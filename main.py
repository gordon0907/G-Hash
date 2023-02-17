import hashlib
import multiprocessing
import os
import subprocess
import sys
import tkinter as tk
from collections import Counter
from operator import itemgetter
from threading import Thread
from tkinter import filedialog
from tkinter import font
from tkinter import ttk

import darkdetect
from joblib import Parallel, delayed
from natsort import os_sorted  # optional dependencies: fastnumbers, PyICU
from ttkthemes import ThemedStyle


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("G-Hash")
        # self.iconbitmap()
        self.geometry('1280x726')  # 720 cannot show last item
        # font.nametofont('TkDefaultFont').configure(family='Courier New')
        if darkdetect.isDark():
            ThemedStyle(self).set_theme('black')

        """
        initialize treeview
        """
        columns = ('Filename', 'MD5', 'SHA-256', 'SHA-512', 'Full Path', 'File Size', 'Identical', 'Extension')
        self.tv = ttk.Treeview(self, columns=columns, show='headings')  # show='headings': hide '#0' column
        for col, width in zip(columns, (250, 250, 250, 250, 300, 100, 75, 75)):
            self.tv.column(col, stretch=False, width=width)  # anchor, minwidth, stretch, width
            self.tv.heading(col, text=col, anchor=tk.W, command=lambda col_=col: self.sort_column(col_, reverse=False))

        """
        top bar
        """
        top = ttk.Frame(self)
        self.button_1 = tk.Button(self, command=self.askopenfiles, text="+ Files")
        self.button_2 = tk.Button(self, command=self.askdirectory, text="+ Directory")
        self.button_3 = tk.Button(self, command=self.refresh_treeview, text="↻")
        self.button_4 = tk.Button(self, command=self.empty_treeview, text="Clear")
        self.progress_bar = ttk.Progressbar(self, mode='determinate')

        """
        bottom bar
        """
        bottom = ttk.Frame(self)
        self.label_1, self.label_2 = tk.StringVar(), tk.StringVar()
        self.label_1.set("0 file(s)")
        self.label_2.set("0 selected")
        label_1 = ttk.Label(self, textvariable=self.label_1)
        label_2 = ttk.Label(self, textvariable=self.label_2)

        """
        scrollbar
        """
        scrollbar_y = ttk.Scrollbar(self, command=self.tv.yview)
        scrollbar_x = ttk.Scrollbar(self, command=self.tv.xview, orient=tk.HORIZONTAL)
        self.tv.config(xscrollcommand=scrollbar_x.set, yscrollcommand=scrollbar_y.set)

        """
        pack widgets
        """
        top.pack(fill=tk.X, side=tk.TOP)
        self.button_1.pack(side=tk.LEFT, in_=top)
        self.button_2.pack(side=tk.LEFT, in_=top)
        self.button_3.pack(side=tk.LEFT, in_=top)
        self.button_4.pack(side=tk.RIGHT, in_=top)
        self.progress_bar.pack(expand=True, fill=tk.X, padx=2, pady=2, in_=top)

        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        label_1.pack(side=tk.LEFT, in_=bottom)
        label_2.pack(side=tk.RIGHT, in_=bottom)

        scrollbar_y.pack(fill=tk.Y, side=tk.RIGHT)
        scrollbar_x.pack(fill=tk.X, side=tk.BOTTOM)
        self.tv.pack(expand=True, fill=tk.BOTH)

        """
        menu
        """
        self.header_menu = tk.Menu(self, tearoff=0)
        self.selected_column = None
        self.header_menu.add_command(command=lambda: self.adaptive_column_width(all_=False),
                                     label="Size Column to Fit")
        self.header_menu.add_command(command=lambda: self.adaptive_column_width(all_=True),
                                     label="Size All Columns to Fit")

        """
        tag colors
        """
        self.init_tag()

        """
        bind events
        """
        self.bind('<Configure>', self.resize)
        self.tv.bind('<Button-3>' if os.name == 'nt' else '<Button-2>', self.right_click_action)
        self.tv.bind('<<TreeviewSelect>>', self.update_label_2)
        self.tv.bind('<Double-Button-1>', self.browse)
        self.tv.bind('<BackSpace>', self.delete)
        self.tv.bind('<Delete>', self.delete)

    def askopenfiles(self):
        list_ = [_.name for _ in filedialog.askopenfiles()]
        list_ and self.main(list_)

    def askdirectory(self):
        list_ = []
        for dirpath, dirnames, filenames in os.walk(filedialog.askdirectory()):
            for filename in filenames:
                list_.append(os.path.join(dirpath, filename))
        list_ and self.main(list_)

    def refresh_treeview(self):
        list_ = filter(os.path.isfile, [self.tv.set(iid)['Full Path'] for iid in self.tv.get_children()])
        self.empty_treeview()
        list_ and self.main(list_)

    def empty_treeview(self):
        self.tv.delete(*self.tv.get_children())
        self.update_label_1()
        self.reset_progress_bar()

    def adaptive_column_width(self, all_):
        buffer_width = font.nametofont('TkDefaultFont').measure('000')
        if all_:  # all columns
            dict_ = {col: [] for col in self.tv['columns']}
            for iid in self.tv.get_children():
                for col, val in self.tv.set(iid).items():
                    dict_[col].append(val)

            for col, list_ in dict_.items():
                list_.append(col)
                list_ = [font.nametofont('TkDefaultFont').measure(_) for _ in list_]
                dict_[col] = max(list_) + buffer_width
            for col, width in dict_.items():
                self.tv.column(col, width=width)
        else:  # selected column
            list_ = [self.tv.set(iid)[self.selected_column] for iid in self.tv.get_children()]
            list_.append(self.selected_column)
            self.tv.column(self.selected_column,
                           width=max(font.nametofont('TkDefaultFont').measure(_) for _ in list_) + buffer_width)

    def init_tag(self):
        colors = {'0': '#ffe8ff',
                  '1': '#ffffe8',
                  '2': '#e8ffff',
                  '3': '#e8d0ff',
                  '4': '#e8ffd0',
                  '5': '#d0ffe8',
                  '6': '#d0e8ff',
                  '7': '#e8e8ff'}
        for tag, color in colors.items():
            self.tv.tag_configure(tagname=tag, foreground='#000000', background=color)

    def resize(self, event):
        try:
            window_width = self.tv.winfo_width() - 4  # fit for Windows
        except tk.TclError:
            return
        total_column_width = sum(self.tv.column(col)['width'] for col in self.tv['column'])
        if window_width > total_column_width:
            gap = window_width - total_column_width
            for col, default in ('Full Path', 300), ('Filename', 250):
                difference = self.tv.column(col)['width'] - default
                if difference < 0:
                    if gap > -difference:
                        self.tv.column(col, width=default)
                        gap -= difference
                    else:
                        self.tv.column(col, width=default + difference + gap)
                        break
            else:
                gap //= 2
                self.tv.column('Filename', width=self.tv.column('Filename')['width'] + gap)
                self.tv.column('Full Path', width=self.tv.column('Full Path')['width'] + gap)

    def right_click_action(self, event):
        """
        show menu when heading is clicked
        """
        if self.tv.identify_region(event.x, event.y) == 'heading':
            self.selected_column = self.tv['columns'][int(self.tv.identify_column(event.x)[1:]) - 1]
            self.header_menu.tk_popup(event.x_root, event.y_root)

    def browse(self, event):
        if self.tv.identify_region(event.x, event.y) == 'cell' and len(self.tv.selection()) == 1:
            path = os.path.dirname(self.tv.set(*self.tv.selection())['Full Path'])
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                subprocess.Popen(['open', path])

    def delete(self, event):
        self.tv.delete(*self.tv.selection())
        self.update_label_1()

    def update_label_1(self):
        self.label_1.set(f"{len(self.tv.get_children())} file(s)")

    def update_label_2(self, event=None):
        self.label_2.set(f"{len(self.tv.selection())} selected")

    def main(self, list_):
        def parallel():
            nonlocal results
            if getattr(sys, 'frozen', False):  # executable
                results = Parallel(n_jobs=-1, backend='threading')(delayed(self.hash_)(path) for path in list_)
            else:  # debug
                from tqdm import tqdm
                results = Parallel(n_jobs=-1, backend='threading')(delayed(self.hash_)(path) for path in tqdm(list_))

        """
        disable the buttons
        """
        for button in (self.button_1, self.button_2, self.button_3, self.button_4):
            button['state'] = tk.DISABLED

        list_ = os_sorted(os.path.normpath(_) for _ in list_)
        self.reset_progress_bar(len(list_))
        results = []
        process = Thread(target=parallel, daemon=True)
        process.start()

        """
        update progress bar
        """
        while self.progress_bar['value'] < len(list_):
            self.progress_bar['value'] = progress_bar_value
            self.update_idletasks()
            self.update()
        process.join()

        """
        insert new items
        """
        for result in results:
            # result: (path, MD5, SHA-256, SHA-512, size)
            iid = result[0]
            filename = os.path.basename(result[0])
            values = (filename, result[1], result[2], result[3], result[0],
                      f'{result[4]:,}', '', filename.split('.')[-1])
            if self.tv.exists(iid):
                self.tv.item(iid, tags='', values=values)
                self.tv.move(iid, parent='', index=tk.END)
            else:
                self.tv.insert(parent='', index=tk.END, iid=iid, values=values)

        """
        coloring
        """
        dict_ = {iid: itemgetter('MD5', 'SHA-256', 'SHA-512')(self.tv.set(iid)) for iid in self.tv.get_children()}
        list_ = [value for value, count in Counter(dict_.values()).items() if count > 1]
        for iid, value in dict_.items():
            if value in list_:
                index = list_.index(value)
                self.tv.set(iid, column='Identical', value=index + 1)
                self.tv.item(iid, tags=f'{index % 8}')

        """
        sort
        """
        for col in self.tv['columns']:
            text = self.tv.heading(col)['text']
            if '↓' in text:
                self.sort_column(col, reverse=True)
                break
            elif '↑' in text:
                self.sort_column(col, reverse=False)
                break

        """
        update label
        """
        self.update_label_1()

        """
        enable the buttons
        """
        for button in (self.button_1, self.button_2, self.button_3, self.button_4):
            button['state'] = tk.NORMAL

    def reset_progress_bar(self, maximum=0):
        global progress_bar_value
        progress_bar_value = 0
        self.progress_bar['value'] = progress_bar_value
        self.progress_bar['maximum'] = maximum
        self.update_idletasks()

    def sort_column(self, col, reverse):
        # sort by 'col' then 'Filename'
        list_ = [itemgetter(col, 'Filename')(self.tv.set(iid)) + (iid,) for iid in self.tv.get_children()]
        list_ = os_sorted(list_, reverse=reverse)
        for val, filename, iid in list_:
            self.tv.move(item=iid, parent='', index=tk.END)

        for col_ in self.tv['columns']:
            self.tv.heading(col_, text=col_)
        self.tv.heading(col, text=f"{col} {'↓' if reverse else '↑'}",
                        command=lambda: self.sort_column(col, not reverse))

    @staticmethod
    def hash_(path, chunk_size=1024 ** 2):  # 1 MiB
        global progress_bar_value

        size = os.path.getsize(path)
        if not size:
            progress_bar_value += 1
            return path, '', '', '', 0

        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        sha512 = hashlib.sha512()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                md5.update(chunk)
                sha256.update(chunk)
                sha512.update(chunk)
        progress_bar_value += 1
        return path, md5.hexdigest(), sha256.hexdigest(), sha512.hexdigest(), size


def main():
    application = Application()
    application.mainloop()


if __name__ == '__main__':
    multiprocessing.freeze_support()  # prevent joblib.Parallel re-runs the program when freezing on macOS

    progress_bar_value = 0
    main()
