import json

from fastapi.templating import Jinja2Templates

from app.i18n import dir_for, js_bundle, lang_href, locale_from_request, t as translate


def _js_json(locale: str) -> str:
    raw = json.dumps(js_bundle(locale), ensure_ascii=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e")


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
        context["i18n_js_json"] = _js_json(locale)
        context["lang_href"] = lambda lang: lang_href(request, lang)
        return super().TemplateResponse(request, name, context, **kwargs)


templates = I18nTemplates(directory="app/templates")
