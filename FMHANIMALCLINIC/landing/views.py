from django.shortcuts import render


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
