import sys

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )
sys.path.append("pytavia_modules/view" )

from flask          import render_template


class view_welcome:

    def __init__(self):
        pass
    # end def

    def html(self):
        # Render a minimal welcome page without DB/config dependencies
        return render_template(
            "welcome/index.html",
            core_script         = "",
            core_css            = "",
            core_dialog_message = "",
            core_display        = {},
            core_footer         = "",
        )
    # end def

# end class
