from fastapi.templating import Jinja2Templates

from app.i18n import dir_for, js_bundle, lang_href, locale_from_request, t as translate


class I18nTemplates(Jinja2Templates):
    def TemplateResponse(self, request, name, context=None, **kwargs):
        context = dict(context or {})
        locale = locale_from_request(request)
        context.setdefault("request", request)
        context["locale"] = locale
        context["html_lang"] = locale
        context["html_dir"] = dir_for(locale)
        context["t"] = lambda key, **kw: translate(locale, key, **kw)
        context["i18n_js"] = js_bundle(locale)
        context["lang_href"] = lambda lang: lang_href(request, lang)
        return super().TemplateResponse(request, name, context, **kwargs)


templates = I18nTemplates(directory="app/templates")
