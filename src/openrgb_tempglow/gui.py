"""tempglow: GTK4 / libadwaita settings app.

The GUI only edits config.json; the tempglowd service picks up every change immediately.
"""
import copy
import subprocess
import sys
import time
from datetime import datetime

from . import APP_ID, SERVICE_NAME, __version__, config, schedule
from .i18n import _

PART_LABELS = {
    "case": "Case / Motherboard",
    "fans": "Fans",
    "gpu": "Graphics card",
    "ram": "RAM",
}
EFFECT_LABELS = {"static": "Static", "breathing": "Breathing", "rainbow": "Rainbow", "off": "Off"}
ASSIGN_CHOICES = list(config.PARTS) + [config.NONE]
ACTION_LABELS = {"off": "Turn off", "dim": "Dim", "lighting": "Custom lighting"}
WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
SAVE_DELAY_MS = 80
STATUS_POLL_S = 2
HEARTBEAT_STALE_S = 15


def main(argv=None):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk

    def to_rgba(hex_color):
        c = Gdk.RGBA()
        c.parse(hex_color)
        return c

    def from_rgba(rgba):
        return config.rgb_to_hex(*(round(x * 255) for x in (rgba.red, rgba.green, rgba.blue)))

    def string_list(items):
        return Gtk.StringList.new([_(i) for i in items])

    def scale_row(title, on_change, value=None, lo=0, hi=100):
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        if value is not None:
            scale.set_value(value)  # before connecting, so building the row doesn't save
        scale.set_hexpand(True)
        scale.set_size_request(160, -1)
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.connect("value-changed", on_change)
        row = Adw.ActionRow(title=title)
        row.add_suffix(scale)
        return scale, row

    class PartControls:
        """Effect / color / brightness / speed rows. Calls on_change(values) when edited.

        `add` places each row, e.g. a PreferencesGroup's add or an ExpanderRow's add_row.
        """

        def __init__(self, add, values, on_change):
            self.values = values
            self.on_change = on_change
            self._updating = False

            self.effect = Adw.ComboRow(title=_("Effect"),
                                       model=string_list(EFFECT_LABELS[e] for e in config.EFFECTS))
            self.effect.connect("notify::selected", self._changed)
            add(self.effect)

            self.color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False),
                                               valign=Gtk.Align.CENTER)
            self.color.connect("notify::rgba", self._changed)
            self.color_row = Adw.ActionRow(title=_("Color"))
            self.color_row.add_suffix(self.color)
            self.color_row.set_activatable_widget(self.color)
            add(self.color_row)

            self.brightness, self.brightness_row = scale_row(_("Brightness"), self._changed)
            add(self.brightness_row)
            self.speed, self.speed_row = scale_row(_("Speed"), self._changed)
            add(self.speed_row)
            self.rows = (self.effect, self.color_row, self.brightness_row, self.speed_row)
            self.set_values(values)

        def set_values(self, values):
            self._updating = True
            self.values = values
            self.effect.set_selected(config.EFFECTS.index(values["effect"]))
            self.color.set_rgba(to_rgba(values["color"]))
            self.brightness.set_value(values["brightness"])
            self.speed.set_value(values["speed"])
            self._update_sensitivity()
            self._updating = False

        def _update_sensitivity(self):
            effect = config.EFFECTS[self.effect.get_selected()]
            self.color_row.set_sensitive(effect in ("static", "breathing"))
            self.brightness_row.set_sensitive(effect != "off")
            self.speed_row.set_sensitive(effect in ("breathing", "rainbow"))

        def _changed(self, *_args):
            self._update_sensitivity()
            if self._updating:
                return
            self.values.update({
                "effect": config.EFFECTS[self.effect.get_selected()],
                "color": from_rgba(self.color.get_rgba()),
                "brightness": int(self.brightness.get_value()),
                "speed": int(self.speed.get_value()),
            })
            self.on_change(self.values)

    class Window(Adw.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="OpenRGB Tempglow",
                             default_width=600, default_height=840,
                             width_request=360, height_request=400)
            self.cfg = config.load()
            self._save_pending = False
            self._zone_keys = None
            self.status = {}

            toolbar = Adw.ToolbarView()
            header = Adw.HeaderBar()
            self.stack = Adw.ViewStack()
            switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
            header.set_title_widget(switcher)
            header.pack_end(self._build_menu())
            toolbar.add_top_bar(header)

            self.banner = Adw.Banner()
            self.banner.connect("button-clicked", lambda *_a: self.start_service())
            toolbar.add_top_bar(self.banner)

            self.toast = Adw.ToastOverlay(child=self.stack)
            toolbar.set_content(self.toast)
            bottom = Adw.ViewSwitcherBar(stack=self.stack)
            toolbar.add_bottom_bar(bottom)
            self.set_content(toolbar)

            # Collapse the header switcher into a bottom bar on narrow windows
            bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 500sp"))
            bp.add_setter(switcher, "visible", False)
            bp.add_setter(bottom, "reveal", True)
            self.add_breakpoint(bp)

            self.lighting_page = self._build_lighting_page()
            self.stack.add_titled_with_icon(self.lighting_page, "lighting", _("Lighting"),
                                            "weather-clear-symbolic")
            # Stable container so the tab keeps its position when the zone list is rebuilt
            self.devices_bin = Adw.Bin()
            self.stack.add_titled_with_icon(self.devices_bin, "devices", _("Devices"),
                                            "computer-symbolic")
            # Rebuilt when schedules are added or removed
            self.schedule_bin = Adw.Bin()
            self.rebuild_schedule_page()
            self.stack.add_titled_with_icon(self.schedule_bin, "schedule", _("Schedule"),
                                            "alarm-symbolic")
            self.alerts_page = self._build_alerts_page()
            self.stack.add_titled_with_icon(self.alerts_page, "alerts", _("Alerts"),
                                            "dialog-warning-symbolic")

            self.refresh_status()
            GLib.timeout_add_seconds(STATUS_POLL_S, self.refresh_status)

        # ---------- header menu ----------
        def _build_menu(self):
            menu = Gio.Menu()
            menu.append(_("Restart service"), "win.restart-service")
            menu.append(_("Reset to defaults"), "win.reset")
            menu.append(_("About"), "win.about")
            for name, cb in (("restart-service", lambda *_a: self.start_service(restart=True)),
                             ("reset", self.on_reset), ("about", self.on_about)):
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", cb)
                self.add_action(action)
            return Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)

        # ---------- lighting ----------
        def _build_lighting_page(self):
            page = Adw.PreferencesPage()
            group = Adw.PreferencesGroup(title=_("All parts"),
                                         description=_("Changes here apply to every part at once"))
            self.all_controls = PartControls(group.add, dict(self.cfg["parts"]["case"]), self.on_all_change)
            page.add(group)

            self.part_groups, self.part_controls = {}, {}
            for part in config.PARTS:
                group = Adw.PreferencesGroup(title=_(PART_LABELS[part]))
                self.part_controls[part] = PartControls(
                    group.add, self.cfg["parts"][part], lambda v, p=part: self.on_part_change(p, v))
                self.part_groups[part] = group
                page.add(group)
            return page

        def on_all_change(self, values):
            for part, pc in self.part_controls.items():
                self.cfg["parts"][part].update(values)
                pc.set_values(self.cfg["parts"][part])
            self.schedule_save()

        def on_part_change(self, part, values):
            self.cfg["parts"][part] = values
            self.schedule_save()

        # ---------- schedule ----------
        def rebuild_schedule_page(self, expand=None):
            page = Adw.PreferencesPage()
            group = Adw.PreferencesGroup(
                title=_("Schedules"),
                description=_("During each time window the selected parts change. Where schedules "
                              "overlap, the lower one wins. Overheat alerts still show."))
            add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_("Add schedule"),
                             valign=Gtk.Align.CENTER, css_classes=["flat"])
            add.connect("clicked", self.on_add_schedule)
            group.set_header_suffix(add)
            page.add(group)

            self.schedule_rows = []
            if not self.cfg["schedules"]:
                group.add(Adw.ActionRow(title=_("No schedules yet"),
                                        subtitle=_("Press + to turn lights off, dim them or change "
                                                   "their color at set times")))
            for i, rule in enumerate(self.cfg["schedules"]):
                group.add(self._build_schedule_row(i, rule, expanded=(i == expand)))
            self.update_schedule_rows()
            self.schedule_bin.set_child(page)

        def _build_schedule_row(self, index, rule, expanded):
            exp = Adw.ExpanderRow(expanded=expanded)
            switch = Gtk.Switch(active=rule["enabled"], valign=Gtk.Align.CENTER,
                                tooltip_text=_("Enabled"))
            switch.connect("notify::active", lambda w, _p: self.set_rule(rule, "enabled", w.get_active()))
            exp.add_suffix(switch)

            name = Adw.EntryRow(title=_("Name"), text=rule["name"])
            name.connect("changed", lambda w: self.set_rule(rule, "name", w.get_text()))
            exp.add_row(name)
            exp.add_row(self._time_row(_("Start"), rule, "start"))
            exp.add_row(self._time_row(_("End"), rule, "end"))
            exp.add_row(self._days_row(rule))

            for part in config.PARTS:
                sw = Adw.SwitchRow(title=_(PART_LABELS[part]), active=part in rule["parts"])
                sw.connect("notify::active", self.on_rule_part, rule, part)
                exp.add_row(sw)

            action = Adw.ComboRow(title=_("Action"),
                                  model=string_list(ACTION_LABELS[a] for a in schedule.ACTIONS))
            action.set_selected(schedule.ACTIONS.index(rule["action"])
                                if rule["action"] in schedule.ACTIONS else 0)
            exp.add_row(action)

            _dim, dim_row = scale_row(_("Brightness"),
                                      lambda w: self.set_rule(rule, "dim", int(w.get_value())),
                                      value=rule["dim"])
            dim_row.set_subtitle(_("% of usual"))
            exp.add_row(dim_row)
            lighting = PartControls(exp.add_row, rule["lighting"],
                                    lambda v: self.set_rule(rule, "lighting", v))

            def show_action_rows(*_args):
                a = schedule.ACTIONS[action.get_selected()]
                dim_row.set_visible(a == "dim")
                for row in lighting.rows:
                    row.set_visible(a == "lighting")

            def on_action(*_args):
                show_action_rows()
                self.set_rule(rule, "action", schedule.ACTIONS[action.get_selected()])

            action.connect("notify::selected", on_action)
            show_action_rows()

            delete = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                tooltip_text=_("Delete schedule"), css_classes=["flat", "error"])
            delete.connect("clicked", lambda *_a: self.on_delete_schedule(index))
            delete_row = Adw.ActionRow(title=_("Delete schedule"))
            delete_row.add_suffix(delete)
            delete_row.set_activatable_widget(delete)
            exp.add_row(delete_row)

            self.schedule_rows.append((exp, rule))
            return exp

        def _time_row(self, title, rule, key):
            try:
                h, m = divmod(schedule.parse_hhmm(rule[key]), 60)
            except (ValueError, AttributeError):
                h, m = 0, 0
            row = Adw.ActionRow(title=title)
            box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER, margin_top=6, margin_bottom=6)
            spins = []
            for value, hi in ((h, 23), (m, 59)):
                spin = Gtk.SpinButton.new_with_range(0, hi, 1)
                spin.set_orientation(Gtk.Orientation.VERTICAL)  # compact, like GNOME Clocks
                spin.set_wrap(True)
                spin.set_numeric(True)
                spin.set_value(value)
                spin.connect("output", self._pad_spin)
                spins.append(spin)
            box.append(spins[0])
            box.append(Gtk.Label(label=":"))
            box.append(spins[1])

            def changed(*_args):
                hh, mm = (int(s.get_value()) for s in spins)
                self.set_rule(rule, key, f"{hh:02d}:{mm:02d}")

            for spin in spins:
                spin.connect("value-changed", changed)
            row.add_suffix(box)
            return row

        @staticmethod
        def _pad_spin(spin):
            spin.set_text(f"{int(spin.get_value()):02d}")
            return True

        def _days_row(self, rule):
            # No title: seven day buttons plus a label don't fit on narrow windows
            box = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER, margin_top=8, margin_bottom=8,
                          tooltip_text=_("Days"))
            for day, label in enumerate(WEEKDAYS):
                btn = Gtk.ToggleButton(label=_(label), active=day in rule["days"],
                                       css_classes=["circular", "day-toggle"])
                btn.connect("toggled", self.on_rule_day, rule, day)
                box.append(btn)
            return Adw.PreferencesRow(child=box, activatable=False, title=_("Days"))

        def set_rule(self, rule, key, value):
            rule[key] = value
            self.update_schedule_rows()
            self.schedule_save()

        def on_rule_part(self, sw, _pspec, rule, part):
            parts = set(rule["parts"])
            (parts.add if sw.get_active() else parts.discard)(part)
            self.set_rule(rule, "parts", [p for p in config.PARTS if p in parts])

        def on_rule_day(self, btn, rule, day):
            days = set(rule["days"])
            (days.add if btn.get_active() else days.discard)(day)
            self.set_rule(rule, "days", sorted(days))

        def on_add_schedule(self, *_args):
            self.cfg["schedules"].append(schedule.new_rule())
            self.schedule_save()
            self.rebuild_schedule_page(expand=len(self.cfg["schedules"]) - 1)

        def on_delete_schedule(self, index):
            del self.cfg["schedules"][index]
            self.schedule_save()
            self.rebuild_schedule_page()

        def update_schedule_rows(self):
            active = set(schedule.active_rules(self.cfg["schedules"], datetime.now()))
            for i, (exp, rule) in enumerate(self.schedule_rows):
                exp.set_title(GLib.markup_escape_text(rule["name"].strip())
                              or _("Schedule {n}").format(n=i + 1))
                exp.set_subtitle(self.describe_rule(rule, i in active))

        @staticmethod
        def describe_rule(rule, active):
            days = rule["days"]
            if len(days) == 7:
                when = _("Every day")
            elif days == [0, 1, 2, 3, 4]:
                when = _("Weekdays")
            elif days == [5, 6]:
                when = _("Weekends")
            elif not days:
                when = _("No days")
            else:
                when = " ".join(_(WEEKDAYS[d]) for d in days)
            parts = (_("All parts") if len(rule["parts"]) == len(config.PARTS) else
                     ", ".join(_(PART_LABELS[p]) for p in rule["parts"]) or _("No parts"))
            action = _(ACTION_LABELS.get(rule["action"], rule["action"]))
            if rule["action"] == "dim":
                action += f" {rule['dim']}%"
            text = f"{rule['start']}–{rule['end']} · {when} · {action} · {parts}"
            if active:
                text += " · " + _("Active now")
            return GLib.markup_escape_text(text)

        # ---------- alerts ----------
        def _build_alerts_page(self):
            oh = self.cfg["overheat"]
            page = Adw.PreferencesPage()
            group = Adw.PreferencesGroup(
                title=_("Overheat alert"),
                description=_("When the CPU or graphics card passes its limit, "
                              "the selected parts switch to the alert color"))
            page.add(group)

            enabled = Adw.SwitchRow(title=_("Enabled"), active=oh["enabled"])
            enabled.connect("notify::active", lambda w, _p: self.set_overheat("enabled", w.get_active()))
            group.add(enabled)

            color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False),
                                          rgba=to_rgba(oh["color"]), valign=Gtk.Align.CENTER)
            color.connect("notify::rgba", lambda w, _p: self.set_overheat("color", from_rgba(w.get_rgba())))
            row = Adw.ActionRow(title=_("Alert color"))
            row.add_suffix(color)
            group.add(row)

            for key, title, lo, hi in (("cpu_hot", "CPU limit (°C)", 50, 110),
                                       ("gpu_hot", "Graphics card limit (°C)", 50, 110),
                                       ("hysteresis", "Return to normal after cooling by (°C)", 1, 30)):
                spin = Adw.SpinRow.new_with_range(lo, hi, 1)
                spin.set_title(_(title))
                spin.set_value(oh[key])
                spin.connect("notify::value", lambda w, _p, k=key: self.set_overheat(k, int(w.get_value())))
                group.add(spin)

            parts_group = Adw.PreferencesGroup(title=_("Parts that change color"))
            for part in config.PARTS:
                sw = Adw.SwitchRow(title=_(PART_LABELS[part]), active=part in oh["parts"])
                sw.connect("notify::active", self.on_overheat_part, part)
                parts_group.add(sw)
            page.add(parts_group)

            temps = Adw.PreferencesGroup(title=_("Current temperatures"))
            self.cpu_temp_row = Adw.ActionRow(title="CPU", subtitle="—")
            self.gpu_temp_row = Adw.ActionRow(title=_("Graphics card"), subtitle="—")
            temps.add(self.cpu_temp_row)
            temps.add(self.gpu_temp_row)
            page.add(temps)
            return page

        def set_overheat(self, key, value):
            self.cfg["overheat"][key] = value
            self.schedule_save()

        def on_overheat_part(self, sw, _pspec, part):
            parts = self.cfg["overheat"]["parts"]
            if sw.get_active() and part not in parts:
                parts.append(part)
            elif not sw.get_active() and part in parts:
                parts.remove(part)
            self.schedule_save()

        # ---------- devices ----------
        def rebuild_devices_page(self, zones):
            page = Adw.PreferencesPage()
            if not zones:
                status = Adw.StatusPage(icon_name="computer-symbolic", title=_("No devices found yet"),
                                        description=_("Lighting zones appear here once the service "
                                                      "connects to OpenRGB."))
                group = Adw.PreferencesGroup()
                group.add(status)
                page.add(group)
            groups = {}
            for z in zones:
                group = groups.get(z["device"])
                if group is None:
                    group = Adw.PreferencesGroup(title=z["device"],
                                                 description=_("Choose which part each lighting zone "
                                                               "belongs to") if not groups else None)
                    groups[z["device"]] = group
                    page.add(group)
                combo = Adw.ComboRow(title=z["zone"],
                                     model=string_list([PART_LABELS[p] for p in config.PARTS]
                                                       + ["Not assigned (off)"]))
                combo.set_selected(ASSIGN_CHOICES.index(z["part"]) if z["part"] in ASSIGN_CHOICES
                                   else len(ASSIGN_CHOICES) - 1)
                combo.connect("notify::selected", self.on_assign, z["key"])
                group.add(combo)
                if z["resizable"]:
                    spin = Adw.SpinRow.new_with_range(max(1, z["leds_min"]), max(1, z["leds_max"]), 1)
                    spin.set_title(f"{z['zone']} · {_('LED count')}")
                    spin.set_subtitle(_("Set this to the number of LEDs connected to the header"))
                    spin.set_value(self.cfg["zone_leds"].get(z["key"], z["leds"]) or 1)
                    spin.connect("notify::value", self.on_zone_leds, z["key"])
                    group.add(spin)

            self.devices_bin.set_child(page)

        def on_assign(self, combo, _pspec, key):
            self.cfg["assignments"][key] = ASSIGN_CHOICES[combo.get_selected()]
            self.schedule_save()

        def on_zone_leds(self, spin, _pspec, key):
            self.cfg["zone_leds"][key] = int(spin.get_value())
            self.schedule_save()

        # ---------- status polling ----------
        def refresh_status(self):
            st = config.load_status()
            self.status = st
            alive = st.get("heartbeat", 0) > time.time() - HEARTBEAT_STALE_S
            orgb = st.get("openrgb", {})
            if not alive:
                self.banner.set_title(_("The lighting service is not running"))
                self.banner.set_button_label(_("Start"))
                self.banner.set_revealed(True)
            elif orgb.get("error") == "openrgb-not-found":
                self.banner.set_title(_("OpenRGB was not found. Install OpenRGB 1.0 or newer."))
                self.banner.set_button_label(None)
                self.banner.set_revealed(True)
            elif not orgb.get("connected"):
                self.banner.set_title(_("Connecting to OpenRGB…"))
                self.banner.set_button_label(None)
                self.banner.set_revealed(True)
            else:
                self.banner.set_revealed(False)

            zones = st.get("zones", []) if alive else []
            # Rebuild only when the set of zones changes, not on every edit (keeps scroll position)
            keys = [(z["key"], z["resizable"]) for z in zones]
            if keys != self._zone_keys:
                self._zone_keys = keys
                self.rebuild_devices_page(zones)

            present = st.get("parts_present", {})
            for part, group in self.part_groups.items():
                group.set_description(None if present.get(part, not alive) else
                                      _("No lights assigned to this part yet (see Devices)"))

            self.update_schedule_rows()

            temps = st.get("temps", {})
            for row, val in ((self.cpu_temp_row, temps.get("cpu")), (self.gpu_temp_row, temps.get("gpu"))):
                row.set_subtitle(f"{val:.0f} °C" if alive and val is not None else _("not available"))
            return GLib.SOURCE_CONTINUE

        def start_service(self, restart=False):
            subprocess.run(["systemctl", "--user", "restart" if restart else "start", SERVICE_NAME],
                           check=False)
            GLib.timeout_add_seconds(1, lambda: self.refresh_status() and False)

        # ---------- reset / about ----------
        def on_reset(self, *_args):
            dialog = Adw.AlertDialog(heading=_("Reset to defaults?"),
                                     body=_("Lighting, schedule, alert and device settings will all be reset."))
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("reset", _("Reset"))
            dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_reset_response)
            dialog.present(self)

        def _on_reset_response(self, _dialog, response):
            if response != "reset":
                return
            config.save(copy.deepcopy(config.DEFAULT))
            self.get_application().rebuild_window(toast=_("Settings reset"))

        def on_about(self, *_args):
            about = Adw.AboutDialog(
                application_name="OpenRGB Tempglow", application_icon=APP_ID, version=__version__,
                developer_name="Yoobin Kim", license_type=Gtk.License.GPL_3_0,
                website="https://github.com/yoobinkim541/openrgb-tempglow",
                issue_url="https://github.com/yoobinkim541/openrgb-tempglow/issues")
            about.present(self)

        # Coalesce slider drags into one write per SAVE_DELAY_MS
        def schedule_save(self):
            if not self._save_pending:
                self._save_pending = True
                GLib.timeout_add(SAVE_DELAY_MS, self._do_save)

        def _do_save(self):
            self._save_pending = False
            config.save(self.cfg)
            return GLib.SOURCE_REMOVE

    class App(Adw.Application):
        def __init__(self):
            super().__init__(application_id=APP_ID)
            self.win = None

        def do_startup(self):
            Adw.Application.do_startup(self)
            css = Gtk.CssProvider()
            css.load_from_string(
                ".day-toggle { min-width: 30px; min-height: 30px; padding: 0; }"
                ".day-toggle:checked { background: @accent_bg_color; color: @accent_fg_color; }")
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        def do_activate(self):
            Gtk.Window.set_default_icon_name(APP_ID)
            if self.win is None:
                self.win = Window(self)
            self.win.present()

        def rebuild_window(self, toast=None):
            old, self.win = self.win, Window(self)
            self.win.present()
            old.destroy()
            if toast:
                self.win.toast.add_toast(Adw.Toast(title=toast))

    return App().run(sys.argv if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
