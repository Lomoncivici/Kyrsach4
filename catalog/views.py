from django.shortcuts import render
from uuid import UUID

class Item:
    def __init__(self, id, title, backdrop_url, poster_url, rating=8.0,
                 can_watch=True, requires_subscription=False, year=2024, kind='movie'):
        self.id = id; self.title = title; self.backdrop_url = backdrop_url
        self.poster_url = poster_url; self.rating = rating
        self.can_watch = can_watch; self.requires_subscription = requires_subscription
        self.year = year; self.kind_display = 'Фильм' if kind=='movie' else kind
        self.type = kind
        self.description = 'Краткое описание для демонстрации интерфейса.'
        self.country = 'Россия'
        self.age_limit = 18
        self.langs_display = 'Rus'

MOCK = [
    Item('11111111-1111-1111-1111-111111111111','Контент 1',
         '/static/img/hero1.jpg','/static/img/post1.jpg'),
    Item('22222222-2222-2222-2222-222222222222','Контент 2',
         '/static/img/hero2.jpg','/static/img/post2.jpg', kind='anime'),
]

def main(request):
    ctx = {
        'hero_items': MOCK,
        'continue_watch': MOCK[:2],
        'watchlist': MOCK[:2],
        'anime': MOCK,
        'series': MOCK,
        'movies': MOCK,
        'cartoons': MOCK,
    }
    return render(request, 'catalog/main.html', ctx)

def content_detail(request, pk: UUID):
    item = next((x for x in MOCK if str(x.id)==str(pk)), MOCK[0])
    return render(request, 'catalog/content_detail.html', {'content': item})
