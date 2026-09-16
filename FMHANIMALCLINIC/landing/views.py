from django.http import HttpResponse
from django.shortcuts import render


PUBLIC_PAGES = ('/', '/about/', '/services/', '/contact/')


def home_view(request):
    """Landing / Home page"""
    return render(request, 'landing/home.html')


def about_view(request):
    """About Us page"""
    return render(request, 'landing/about.html')


def services_view(request):
    """Services page"""
    return render(request, 'landing/services.html')


def contact_view(request):
    """Contact page - branches and branches_json are provided by context processor"""
    return render(request, 'landing/contact.html')


def robots_view(request):
    """Tell search engines which public pages they may crawl."""
    sitemap_url = request.build_absolute_uri('/sitemap.xml')
    content = f'User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /accounts/\nDisallow: /settings/\nSitemap: {sitemap_url}\n'
    return HttpResponse(content, content_type='text/plain')


def sitemap_view(request):
    """Expose the public landing pages to search engines."""
    urls = ''.join(
        f'<url><loc>{request.build_absolute_uri(path)}</loc></url>'
        for path in PUBLIC_PAGES
    )
    content = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HttpResponse(content, content_type='application/xml')
