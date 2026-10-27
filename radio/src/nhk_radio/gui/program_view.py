"""Program list widgets and their local event bindings."""

from collections.abc import Callable
from typing import Protocol

from .toolkit import tk, ttk


class ProgramListActions(Protocol):
    def _open_ondemand_site(self, event=None): ...
    def _bind_tooltip(self, widget, text: str): ...
    def _on_program_filter_change(self, *args): ...
    def _clear_program_search(self, event=None): ...
    def _focus_program_tree_from_search(self, event=None): ...
    def _commit_program_search(self, event=None): ...
    def _on_program_search_history_selected(self, event=None): ...
    def _on_program_search_focus_in(self, event=None): ...
    def _on_program_search_focus_out(self, event=None): ...
    def _toggle_program_sort(self, column: str): ...
    def _on_program_select(self, event=None): ...
    def _on_program_tree_click(self, event=None): ...
    def _on_program_double_click(self, event=None): ...
    def _start_fetch_selected(self, event=None): ...
    def _copy_selected_cell_to_clipboard(self, event=None): ...


class ProgramListView:
    def __init__(
        self,
        parent: ttk.Panedwindow,
        actions: ProgramListActions,
        search_var: tk.StringVar,
        genre_var: tk.StringVar,
        summary_var: tk.StringVar,
        search_history: list[str],
        genre_values: Callable[[], list[str]],
    ) -> None:
        sidebar = ttk.Frame(parent, style="Sidebar.TFrame", padding=16, width=430)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)

        header = ttk.Frame(sidebar, style="SidebarInner.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="番組一覧", style="CardTitleAlt.TLabel").grid(row=0, column=0, sticky="w")
        self.ondemand_link_button = ttk.Button(
            header,
            text="らじる★らじる",
            command=actions._open_ondemand_site,
            style="RajiruLink.TButton",
            cursor="hand2",
        )
        self.ondemand_link_button.grid(row=0, column=1, sticky="e")
        actions._bind_tooltip(self.ondemand_link_button, "聞き逃し検索の公式サイト")

        search = ttk.Frame(sidebar, style="SidebarInner.TFrame")
        search.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        search.columnconfigure(0, weight=1)
        self.genre_combo = ttk.Combobox(search, textvariable=genre_var, values=genre_values(), state="readonly")
        self.genre_combo.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.genre_combo.bind("<<ComboboxSelected>>", actions._on_program_filter_change)
        self.search_entry = ttk.Combobox(search, textvariable=search_var, values=search_history)
        self.search_entry.grid(row=1, column=0, sticky="ew")
        for sequence, callback in (
            ("<Escape>", actions._clear_program_search),
            ("<Down>", actions._focus_program_tree_from_search),
            ("<Return>", actions._commit_program_search),
            ("<<ComboboxSelected>>", actions._on_program_search_history_selected),
            ("<FocusIn>", actions._on_program_search_focus_in),
            ("<FocusOut>", actions._on_program_search_focus_out),
        ):
            self.search_entry.bind(sequence, callback)
        ttk.Label(search, textvariable=summary_var, style="CardMetaAlt.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )

        self.tree = ttk.Treeview(sidebar, columns=("no", "date", "title"), show="headings", selectmode="browse")
        for column, text, anchor in (("no", "No.", "e"), ("date", "更新日", "w"), ("title", "番組", "w")):
            self.tree.heading(column, text=text, anchor=anchor, command=lambda col=column: actions._toggle_program_sort(col))
        self.tree.column("no", width=60, anchor="e", stretch=False)
        self.tree.column("date", width=140, anchor="w", stretch=False)
        self.tree.column("title", width=360, anchor="w")
        scrollbar = ttk.Scrollbar(sidebar, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        parent.add(sidebar, weight=11)

        for sequence, callback in (
            ("<<TreeviewSelect>>", actions._on_program_select),
            ("<ButtonRelease-1>", actions._on_program_tree_click),
            ("<Double-1>", actions._on_program_double_click),
            ("<Return>", actions._start_fetch_selected),
            ("<Control-c>", actions._copy_selected_cell_to_clipboard),
            ("<Command-c>", actions._copy_selected_cell_to_clipboard),
        ):
            self.tree.bind(sequence, callback)
        self.frame = sidebar
