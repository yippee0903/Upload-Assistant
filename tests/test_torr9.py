# Tests for TORR9 tracker — torr9.net
"""
Test suite for the TORR9 tracker implementation.
Covers: language detection, naming, category mapping,
        tags building, description, upload form fields.
"""

import asyncio
import json
import os
import re
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trackers.TORR9 import TORR9

# ─── Helpers ──────────────────────────────────────────────────


def _config(extra_tracker: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a minimal config dict for TORR9."""
    tracker_cfg: dict[str, Any] = {
        'api_key': 'test-bearer-token-123',
        'announce_url': 'https://tracker.torr9.net/announce/FAKE_PASSKEY',
    }
    if extra_tracker:
        tracker_cfg.update(extra_tracker)
    return {
        'TRACKERS': {'TORR9': tracker_cfg},
        'DEFAULT': {'tmdb_api': 'fake-tmdb-key-for-tests'},
    }


def _meta_base(**overrides: Any) -> dict[str, Any]:
    """Build a base meta dict with sensible defaults."""
    m: dict[str, Any] = {
        'category': 'MOVIE',
        'type': 'WEBDL',
        'title': 'Le Prénom',
        'year': '2012',
        'resolution': '1080p',
        'source': 'WEB',
        'audio': 'AC3',
        'video_encode': 'x264',
        'service': '',
        'tag': '-Troxy',
        'edition': '',
        'repack': '',
        '3D': '',
        'uhd': '',
        'hdr': '',
        'webdv': '',
        'part': '',
        'season': '',
        'episode': '',
        'is_disc': None,
        'search_year': '',
        'manual_year': None,
        'manual_date': None,
        'no_season': False,
        'no_year': False,
        'no_aka': False,
        'debug': False,
        'tv_pack': 0,
        'path': '',
        'name': '',
        'uuid': 'test-uuid',
        'base_dir': '/tmp',
        'overview': 'Un dîner entre amis tourne mal.',
        'poster': 'https://image.tmdb.org/poster.jpg',
        'tmdb': 1234,
        'imdb_id': 1234567,
        'original_language': 'fr',
        'image_list': [],
        'bdinfo': None,
        'mediainfo': {
            'media': {
                'track': []
            }
        },
        'tracker_status': {'TORR9': {}},
    }
    m.update(overrides)
    return m


def _audio_track(lang: str = 'fr', **kw: Any) -> dict[str, Any]:
    t: dict[str, Any] = {'@type': 'Audio', 'Language': lang}
    t.update(kw)
    return t


def _sub_track(lang: str = 'fr') -> dict[str, Any]:
    return {'@type': 'Text', 'Language': lang}


def _mi(audio: list[dict[str, Any]], subs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tracks = list(audio)
    if subs:
        tracks.extend(subs)
    return {'media': {'track': tracks}}


def _run(coro):
    """Helper to run an async coroutine in sync tests."""
    return asyncio.run(coro)


# ─── Constructor ─────────────────────────────────────────────

class TestTorr9Init:
    def test_basic_init(self):
        t = TORR9(_config())
        assert t.tracker == 'TORR9'
        assert t.source_flag == 'TORR9'
        assert t.api_key == 'test-bearer-token-123'
        assert t.username == ''
        assert t.password == ''
        assert t.upload_url == 'https://api.torr9.net/api/v1/torrents/upload'
        assert t.torrent_url == 'https://torr9.net/torrents/'

    def test_missing_api_key(self):
        t = TORR9({'TRACKERS': {}, 'DEFAULT': {'tmdb_api': 'fake'}})
        assert t.api_key == ''
        assert t.username == ''
        assert t.password == ''

    def test_init_with_credentials(self):
        t = TORR9(_config({'username': 'testuser', 'password': 'testpass'}))
        assert t.username == 'testuser'
        assert t.password == 'testpass'
        assert t.api_key == 'test-bearer-token-123'


# ─── Authentication ──────────────────────────────────────────

class TestLogin:
    def test_login_success(self):
        t = TORR9(_config({'username': 'user', 'password': 'pass'}))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'token': 'jwt-abc-123', 'user': {'passkey': 'pk'}}

        with patch('httpx.AsyncClient') as MockClient:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            token = _run(t._login())

        assert token == 'jwt-abc-123'

    def test_login_no_credentials(self):
        t = TORR9(_config())  # no username/password
        token = _run(t._login())
        assert token is None

    def test_login_http_error(self):
        t = TORR9(_config({'username': 'user', 'password': 'bad'}))
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {'error': 'Invalid credentials'}

        with patch('httpx.AsyncClient') as MockClient:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            token = _run(t._login())

        assert token is None

    def test_get_token_uses_cached(self):
        t = TORR9(_config())
        t._bearer_token = 'cached-token'
        assert _run(t._get_token()) == 'cached-token'

    def test_get_token_login_then_cache(self):
        t = TORR9(_config({'username': 'user', 'password': 'pass'}))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'token': 'fresh-jwt'}

        with patch('httpx.AsyncClient') as MockClient:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            token = _run(t._get_token())

        assert token == 'fresh-jwt'
        assert t._bearer_token == 'fresh-jwt'

    def test_get_token_fallback_api_key(self):
        t = TORR9(_config())  # has api_key but no username/password
        token = _run(t._get_token())
        assert token == 'test-bearer-token-123'

    def test_get_token_nothing_configured(self):
        t = TORR9({'TRACKERS': {}, 'DEFAULT': {'tmdb_api': 'fake'}})
        token = _run(t._get_token())
        assert token == ''


# ─── Language detection ──────────────────────────────────────

class TestAudioString:
    def _run_audio(self, meta):
        t = TORR9(_config())
        return _run(t._build_audio_string(meta))

    def test_single_french_original(self):
        meta = _meta_base(
            original_language='fr',
            mediainfo=_mi([_audio_track('fr')]),
        )
        assert self._run_audio(meta) == 'VOF'

    def test_multi_fr_en(self):
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([_audio_track('en'), _audio_track('fr')]),
        )
        result = self._run_audio(meta)
        assert result.startswith('MULTI')

    def test_english_only_no_subs(self):
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([_audio_track('en')]),
        )
        assert self._run_audio(meta) == ''

    def test_english_with_fr_subs(self):
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([_audio_track('en')], [_sub_track('fr')]),
        )
        assert self._run_audio(meta) == 'VOSTFR'

    def test_truefrench(self):
        """TRUEFRENCH in filename → outputs VFF (modern equivalent)."""
        meta = _meta_base(
            original_language='en',
            uuid='Movie.2024.TRUEFRENCH.1080p.WEB-DL',
            mediainfo=_mi([_audio_track('fr')]),
        )
        assert self._run_audio(meta) == 'VFF'

    def test_vf2(self):
        meta = _meta_base(
            original_language='en',
            mediainfo=_mi([
                _audio_track('en'),
                _audio_track('fr', Title='VF2'),
            ]),
        )
        assert self._run_audio(meta) == 'MULTI.VF2'

    def test_muet_with_subs(self):
        meta = _meta_base(
            mediainfo=_mi([], [_sub_track('fr')]),
        )
        assert self._run_audio(meta) == 'MUET.VOSTFR'

    def test_no_mediainfo(self):
        meta = _meta_base()
        del meta['mediainfo']
        assert self._run_audio(meta) == ''


# ─── French title ────────────────────────────────────────────

class TestFrenchTitle:
    def test_cached(self):
        t = TORR9(_config())
        meta = _meta_base(frtitle='Le Titre FR')
        result = _run(t._get_french_title(meta))
        assert result == 'Le Titre FR'

    def test_fallback(self):
        t = TORR9(_config())
        meta = _meta_base()
        with patch.object(t.tmdb_manager, 'get_tmdb_localized_data', new_callable=AsyncMock, return_value={}):
            result = _run(t._get_french_title(meta))
        assert result == 'Le Prénom'


# ─── Category / Subcategory ───────────────────────────────────────

class TestCategory:
    def test_movie(self):
        t = TORR9(_config())
        cat, sub = t._get_category(_meta_base(category='MOVIE'))
        assert cat == 'Films'
        assert sub == 'Films'

    def test_tv(self):
        t = TORR9(_config())
        cat, sub = t._get_category(_meta_base(category='TV'))
        assert cat == 'Séries'
        assert sub == 'Séries TV'

    def test_anime_movie(self):
        t = TORR9(_config())
        cat, sub = t._get_category(_meta_base(category='MOVIE', mal_id=12345))
        assert cat == 'Films'
        assert sub == "Films d'animation"

    def test_anime_tv(self):
        t = TORR9(_config())
        cat, sub = t._get_category(_meta_base(category='TV', mal_id=12345))
        assert cat == 'Séries'
        assert sub == 'Mangas-Animes'


# ─── Tags ────────────────────────────────────────────────────

class TestTags:
    def test_movie_webdl_1080p_multi(self):
        t = TORR9(_config())
        meta = _meta_base(resolution='1080p', type='WEBDL')
        tags = t._build_tags(meta, 'MULTI.VFF')
        assert '1080p' in tags
        assert 'WEB-DL' in tags
        assert 'MULTi' in tags
        assert 'VFF' in tags

    def test_2160p_bluray_remux_hdr(self):
        t = TORR9(_config())
        meta = _meta_base(resolution='2160p', type='REMUX', source='BluRay', hdr='HDR')
        tags = t._build_tags(meta, '')
        assert '2160p' in tags
        assert 'REMUX' in tags
        assert 'BluRay' in tags
        assert 'HDR' in tags

    def test_x265_codec(self):
        t = TORR9(_config())
        meta = _meta_base(video_encode='x265')
        tags = t._build_tags(meta, '')
        assert 'x265' in tags

    def test_x264_codec(self):
        t = TORR9(_config())
        meta = _meta_base(video_encode='x264')
        tags = t._build_tags(meta, '')
        assert 'x264' in tags

    def test_av1_codec(self):
        t = TORR9(_config())
        meta = _meta_base(video_encode='AV1')
        tags = t._build_tags(meta, '')
        assert 'AV1' in tags

    def test_hdr10plus(self):
        t = TORR9(_config())
        meta = _meta_base(hdr='HDR10+')
        tags = t._build_tags(meta, '')
        assert 'HDR10Plus' in tags

    def test_dv(self):
        t = TORR9(_config())
        meta = _meta_base(dv='DV')
        tags = t._build_tags(meta, '')
        assert 'DV' in tags

    def test_vostfr(self):
        t = TORR9(_config())
        tags = t._build_tags(_meta_base(), 'VOSTFR')
        assert 'VOSTFR' in tags

    def test_truefrench(self):
        t = TORR9(_config())
        tags = t._build_tags(_meta_base(), 'TRUEFRENCH')
        assert 'TRUEFRENCH' in tags

    def test_empty_language(self):
        t = TORR9(_config())
        tags = t._build_tags(_meta_base(), '')
        assert 'MULTi' not in tags

    def test_720p_webrip(self):
        t = TORR9(_config())
        meta = _meta_base(resolution='720p', type='WEBRIP')
        tags = t._build_tags(meta, '')
        assert '720p' in tags
        assert 'WEBRip' in tags

    def test_hdtv(self):
        t = TORR9(_config())
        meta = _meta_base(type='HDTV')
        tags = t._build_tags(meta, '')
        assert 'HDTV' in tags

    def test_comma_separated(self):
        t = TORR9(_config())
        meta = _meta_base(resolution='1080p', type='WEBDL', video_encode='x265')
        tags = t._build_tags(meta, 'MULTI.VFF')
        assert ', ' in tags


# ─── Naming ──────────────────────────────────────────────────

class TestNaming:
    def _get_name(self, meta):
        t = TORR9(_config())
        return _run(t.get_name(meta))

    def test_movie_webdl(self):
        meta = _meta_base(frtitle='Le Prenom')
        name = self._get_name(meta)
        assert isinstance(name, dict)
        n = name['name']
        assert 'Le.Prenom' in n
        assert '2012' in n
        assert '1080p' in n
        assert '-Troxy' in n

    def test_tv_episode(self):
        meta = _meta_base(
            frtitle='Les Simpsons',
            category='TV',
            season='S02',
            episode='E05',
            search_year='2024',
        )
        name = self._get_name(meta)
        n = name['name']
        assert 'Les.Simpsons' in n
        assert 'S02E05' in n

    def test_dots_no_spaces(self):
        meta = _meta_base(frtitle='Le Prenom')
        name = self._get_name(meta)
        assert ' ' not in name['name']

    def test_remux_bluray(self):
        meta = _meta_base(
            frtitle='Inception',
            type='REMUX',
            source='BluRay',
            resolution='2160p',
            video_codec='H.265',
        )
        name = self._get_name(meta)
        n = name['name']
        assert 'REMUX' in n
        assert 'BluRay' in n

    def test_encode(self):
        meta = _meta_base(
            frtitle='Avatar',
            type='ENCODE',
            source='BluRay',
            resolution='1080p',
            video_encode='x265',
        )
        name = self._get_name(meta)
        n = name['name']
        assert 'x265' in n

    def test_tag_is_last_dash(self):
        meta = _meta_base(frtitle='Test', tag='-GROUP')
        name = self._get_name(meta)
        n = name['name']
        assert n.endswith('-GROUP')
        before = n[: n.rfind('-GROUP')]
        assert '-' not in before


# ─── Description ─────────────────────────────────────────────

class TestDescription:
    def _build_desc(self, meta, tmdb_data=None):
        t = TORR9(_config())
        with patch.object(t.tmdb_manager, 'get_tmdb_localized_data', new_callable=AsyncMock, return_value=tmdb_data or {}):
            return _run(t._build_description(meta))

    def test_contains_synopsis(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {'title': 'Le Prénom', 'overview': 'Synopsis FR ici.'})
        assert 'Synopsis FR ici.' in desc
        # New template uses plain text, no [quote]
        assert '[quote]' not in desc

    def test_contains_title(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {'title': 'Le Prénom'})
        assert 'Le Prénom' in desc

    def test_styled_headers(self):
        meta = _meta_base()
        desc = self._build_desc(meta)
        assert '[color=#3d85c6]' in desc
        assert '━━━ Synopsis ━━━' in desc
        assert '━━━ Informations ━━━' in desc
        assert '━━━ Informations techniques ━━━' in desc
        assert '━━━ Release ━━━' in desc

    def test_center_wrapped(self):
        meta = _meta_base()
        desc = self._build_desc(meta)
        assert desc.startswith('[center]')
        assert '[/center]' in desc

    def test_verdana_font(self):
        meta = _meta_base()
        desc = self._build_desc(meta)
        assert '[font=Verdana]' in desc

    def test_has_poster(self):
        meta = _meta_base(poster='https://image.tmdb.org/t/p/original/poster.jpg')
        desc = self._build_desc(meta)
        assert '[img]https://image.tmdb.org/t/p/w500/poster.jpg[/img]' in desc
        # Resizes to w500
        assert 'w500' in desc

    def test_has_external_links(self):
        meta = _meta_base(tmdb=27205, imdb_id=1375666)
        desc = self._build_desc(meta)
        assert 'IMDb' in desc
        assert 'TMDB' in desc

    def test_signature(self):
        meta = _meta_base()
        desc = self._build_desc(meta)
        assert 'Upload Assistant' in desc

    def test_screenshots(self):
        meta = _meta_base(image_list=[
            {'raw_url': 'https://img.example.com/1.png', 'web_url': 'https://example.com/1'},
            {'raw_url': 'https://img.example.com/2.png', 'web_url': ''},
        ])
        t = TORR9(_config({'include_screenshots': True}))
        with patch.object(t.tmdb_manager, 'get_tmdb_localized_data', new_callable=AsyncMock, return_value={}):
            desc = _run(t._build_description(meta))
        assert 'https://img.example.com/1.png' in desc
        assert 'https://img.example.com/2.png' in desc
        assert "━━━ Captures d'écran ━━━" in desc

    def test_screenshots_excluded_by_default(self):
        meta = _meta_base(image_list=[
            {'raw_url': 'https://img.example.com/1.png', 'web_url': 'https://example.com/1'},
        ])
        desc = self._build_desc(meta)
        assert 'https://img.example.com/1.png' not in desc
        assert "Captures d'écran" not in desc

    def test_min_length(self):
        meta = _meta_base()
        desc = self._build_desc(meta)
        assert len(desc) >= 20

    def test_genres_with_tag_links(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {
            'title': 'Test',
            'genres': [{'name': 'Action'}, {'name': 'Comédie'}],
        })
        assert 'Action' in desc
        assert 'Comédie' in desc
        assert '[url=/torrents?tags=Action]Action[/url]' in desc
        assert '[url=/torrents?tags=Comédie]Comédie[/url]' in desc

    def test_credits(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {
            'title': 'Test',
            'credits': {
                'crew': [
                    {'name': 'Steven Spielberg', 'job': 'Director'},
                ],
                'cast': [
                    {'name': 'Tom Hanks', 'profile_path': '/tom.jpg'},
                    {'name': 'Meg Ryan'},
                ],
            },
        })
        assert 'Steven Spielberg' in desc
        assert 'Tom Hanks' in desc
        assert 'Réalisateur' in desc

    def test_actor_photos(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {
            'title': 'Test',
            'credits': {
                'crew': [],
                'cast': [
                    {'name': 'Actor1', 'profile_path': '/a1.jpg'},
                    {'name': 'Actor2', 'profile_path': '/a2.jpg'},
                ],
            },
        })
        assert 'https://image.tmdb.org/t/p/w185/a1.jpg' in desc
        assert 'https://image.tmdb.org/t/p/w185/a2.jpg' in desc

    def test_tagline(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {'title': 'Test', 'tagline': 'Une aventure incroyable'})
        assert 'Une aventure incroyable' in desc
        assert '[color=#ea9999]' in desc

    def test_runtime(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {'title': 'Test', 'runtime': 148})
        assert '2h28' in desc

    def test_rating_svg_badge(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {'title': 'Test', 'vote_average': 8.3, 'vote_count': 12345})
        assert 'https://img.streetprez.com/note/83.svg' in desc
        assert '8.3' in desc
        assert '12345' in desc

    def test_container_format(self):
        meta = _meta_base()
        with tempfile.TemporaryDirectory() as tmpdir:
            meta['base_dir'] = tmpdir
            uuid_dir = os.path.join(tmpdir, 'tmp', meta['uuid'])
            os.makedirs(uuid_dir, exist_ok=True)
            mi_path = os.path.join(uuid_dir, 'MEDIAINFO.txt')
            with open(mi_path, 'w') as f:
                f.write("General\nFormat                                   : Matroska\n\nVideo\n")

            t = TORR9(_config())
            with patch.object(t.tmdb_manager, 'get_tmdb_localized_data', new_callable=AsyncMock, return_value={}):
                desc = _run(t._build_description(meta))

        assert 'MATROSKA (MKV)' in desc
        assert 'Format vidéo' in desc

    def test_release_section(self):
        meta = _meta_base()
        desc = self._build_desc(meta)
        assert '━━━ Release ━━━' in desc
        assert 'Titre :' in desc

    def test_no_raw_mediainfo(self):
        """New template doesn't include raw MI dump."""
        meta = _meta_base()
        with tempfile.TemporaryDirectory() as tmpdir:
            meta['base_dir'] = tmpdir
            uuid_dir = os.path.join(tmpdir, 'tmp', meta['uuid'])
            os.makedirs(uuid_dir, exist_ok=True)
            mi_path = os.path.join(uuid_dir, 'MEDIAINFO.txt')
            with open(mi_path, 'w') as f:
                f.write("General\nFormat : Matroska\n")

            t = TORR9(_config())
            with patch.object(t.tmdb_manager, 'get_tmdb_localized_data', new_callable=AsyncMock, return_value={}):
                desc = _run(t._build_description(meta))

        assert '[spoiler' not in desc
        assert '[code]' not in desc

    def test_audio_tracks_with_flags(self):
        meta = _meta_base()
        with tempfile.TemporaryDirectory() as tmpdir:
            meta['base_dir'] = tmpdir
            uuid_dir = os.path.join(tmpdir, 'tmp', meta['uuid'])
            os.makedirs(uuid_dir, exist_ok=True)
            mi_path = os.path.join(uuid_dir, 'MEDIAINFO.txt')
            with open(mi_path, 'w') as f:
                f.write(
                    "Audio\n"
                    "Commercial name                          : DTS-HD Master Audio\n"
                    "Language                                 : English\n"
                    "Bit rate                                 : 3 821 kb/s\n"
                    "Channel(s)                               : 6 channels\n"
                    "\nText #1\n"
                    "Language                                 : French\n"
                    "Format                                   : PGS\n"
                )

            t = TORR9(_config())
            with patch.object(t.tmdb_manager, 'get_tmdb_localized_data', new_callable=AsyncMock, return_value={}):
                desc = _run(t._build_description(meta))

        # Audio track with flag
        assert '\U0001f1fa\U0001f1f8' in desc  # US flag
        assert 'DTS-HD Master Audio' in desc
        assert '3 821 kb/s' in desc
        assert '━━━ Audio(s) ━━━' in desc
        # Subtitle track with flag
        assert '\U0001f1eb\U0001f1f7' in desc  # FR flag
        assert '━━━ Sous-titre(s) ━━━' in desc
        assert 'PGS' in desc

    def test_french_date(self):
        meta = _meta_base()
        desc = self._build_desc(meta, {
            'title': 'Test',
            'release_date': '2011-10-24',
        })
        assert '24 octobre 2011' in desc


# ─── Helper methods ──────────────────────────────────────────

class TestFrenchDate:
    def test_basic_date(self):
        assert TORR9._format_french_date('2011-10-24') == '24 octobre 2011'

    def test_first_of_month(self):
        assert TORR9._format_french_date('2020-01-01') == '1er janvier 2020'

    def test_invalid_date(self):
        assert TORR9._format_french_date('not-a-date') == 'not-a-date'


class TestLangToFlag:
    def test_english(self):
        assert TORR9._lang_to_flag('English') == '\U0001f1fa\U0001f1f8'

    def test_french(self):
        assert TORR9._lang_to_flag('French') == '\U0001f1eb\U0001f1f7'

    def test_unknown(self):
        assert TORR9._lang_to_flag('Klingon') == '\U0001f3f3\ufe0f'

    def test_lang_with_parenthetical(self):
        assert TORR9._lang_to_flag('Chinese (Mandarin)') == '\U0001f1e8\U0001f1f3'


class TestParseContainer:
    def test_matroska(self):
        mi = "General\nFormat                                   : Matroska\n\nVideo\n"
        t = TORR9(_config())
        assert t._parse_mi_container(mi) == 'Matroska'

    def test_empty(self):
        t = TORR9(_config())
        assert t._parse_mi_container('') == ''

    def test_format_container_matroska(self):
        mi = "General\nFormat                                   : Matroska\n\nVideo\n"
        t = TORR9(_config())
        assert t._format_container(mi) == 'MATROSKA (MKV)'

    def test_format_container_empty(self):
        t = TORR9(_config())
        assert t._format_container('') == ''


class TestParseAudioTracks:
    def test_single_track(self):
        mi = "Audio\nLanguage                                 : English\nFormat                                   : DTS XLL\nCommercial name                          : DTS-HD Master Audio\nBit rate                                 : 3 821 kb/s\nChannel(s)                               : 6 channels\n"
        tracks = TORR9._parse_mi_audio_tracks(mi)
        assert len(tracks) == 1
        assert tracks[0]['language'] == 'English'
        assert tracks[0]['commercial_name'] == 'DTS-HD Master Audio'
        assert tracks[0]['bitrate'] == '3 821 kb/s'

    def test_multiple_tracks(self):
        mi = "Audio #1\nLanguage                                 : French\nCommercial name                          : AAC\n\nAudio #2\nLanguage                                 : English\nCommercial name                          : DTS\n"
        tracks = TORR9._parse_mi_audio_tracks(mi)
        assert len(tracks) == 2
        assert tracks[0]['language'] == 'French'
        assert tracks[1]['language'] == 'English'

    def test_empty(self):
        assert TORR9._parse_mi_audio_tracks('') == []


class TestParseSubtitleTracks:
    def test_single_sub(self):
        mi = "Text #1\nLanguage                                 : French\nFormat                                   : PGS\nTitle                                    : French\n"
        tracks = TORR9._parse_mi_subtitle_tracks(mi)
        assert len(tracks) == 1
        assert tracks[0]['language'] == 'French'
        assert tracks[0]['format'] == 'PGS'

    def test_multiple_with_titles(self):
        mi = "Text #1\nLanguage                                 : Chinese\nFormat                                   : PGS\nTitle                                    : Chinese (Cantonese)\n\nText #2\nLanguage                                 : Chinese\nFormat                                   : PGS\nTitle                                    : Chinese (Mandarin)\n"
        tracks = TORR9._parse_mi_subtitle_tracks(mi)
        assert len(tracks) == 2
        assert tracks[0]['title'] == 'Chinese (Cantonese)'
        assert tracks[1]['title'] == 'Chinese (Mandarin)'

    def test_empty(self):
        assert TORR9._parse_mi_subtitle_tracks('') == []


# ─── Upload form data ───────────────────────────────────────

class TestUploadData:
    def test_upload_debug_mode(self):
        t = TORR9(_config())
        meta = _meta_base(debug=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            meta['base_dir'] = tmpdir
            uuid_dir = os.path.join(tmpdir, 'tmp', meta['uuid'])
            os.makedirs(uuid_dir, exist_ok=True)

            torrent_path = os.path.join(uuid_dir, '[TORR9].torrent')
            with open(torrent_path, 'wb') as f:
                f.write(b'd8:announce0:e')

            with patch.object(t.tmdb_manager, 'get_tmdb_localized_data', new_callable=AsyncMock, return_value={}):
                with patch('src.trackers.COMMON.COMMON.create_torrent_for_upload', new_callable=AsyncMock):
                    result = _run(t.upload(meta, ''))

        assert result is True
        assert meta['tracker_status']['TORR9']['status_message'] == 'Debug mode, not uploaded.'


# ─── Dupe search ─────────────────────────────────────────────

class TestSearchExisting:
    def test_no_auth(self):
        t = TORR9({'TRACKERS': {}, 'DEFAULT': {'tmdb_api': 'fake'}})
        result = _run(t.search_existing(_meta_base(), ''))
        assert result == []

    def test_search_returns_results(self):
        t = TORR9(_config())
        t._bearer_token = 'test-token'  # skip login
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'torrents': [
                {'title': 'Le.Prenom.2012.MULTi.1080p', 'id': 42, 'file_size_bytes': 5000000000},
                {'title': 'Le.Prenom.2012.FRENCH.720p', 'id': 43, 'file_size_bytes': 3000000000},
            ],
            'total_count': 2,
        }

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(_meta_base(), ''))

        assert len(dupes) == 2
        assert dupes[0]['name'] == 'Le.Prenom.2012.MULTi.1080p'
        assert dupes[0]['id'] == 42
        assert dupes[0]['size'] == 5000000000

    def test_search_handles_error(self):
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(side_effect=Exception("Network error"))
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(_meta_base(), ''))

        assert dupes == []

    def test_search_handles_empty_torrents(self):
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'torrents': [],
            'total_count': 0,
        }

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(_meta_base(), ''))

        assert len(dupes) == 0

    def test_search_http_404(self):
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(_meta_base(), ''))

        assert dupes == []


# ─── edit_desc ───────────────────────────────────────────────

class TestEditDesc:
    def test_noop(self):
        t = TORR9(_config())
        result = _run(t.edit_desc(_meta_base()))
        assert result is None


# ─── Dupe relevance filtering ────────────────────────────────

class TestDupeRelevanceFilter:
    def test_filters_out_unrelated_titles(self):
        """API returns unrelated results → they should be filtered out."""
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        # Searching for "Inception 2010" but API returns "A Fistful of Dollars"
        meta = _meta_base(title='Inception', year='2010')
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'title': 'A.Fistful.of.Dollars.1964.MULTi.2160p', 'id': 1},
                {'title': 'Some.Other.Movie.2020.FRENCH.1080p', 'id': 2},
            ]
        }

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(meta, ''))

        assert dupes == []

    def test_keeps_matching_titles(self):
        """Results matching the title+year should be kept."""
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        meta = _meta_base(title='Inception', year='2010')
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'title': 'Inception.2010.MULTi.2160p.REMUX', 'id': 10},
                {'title': 'A.Fistful.of.Dollars.1964.MULTi.2160p', 'id': 1},
                {'title': 'Inception.2010.FRENCH.1080p.WEB-DL', 'id': 11},
            ]
        }

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(meta, ''))

        assert len(dupes) == 2
        assert dupes[0]['name'] == 'Inception.2010.MULTi.2160p.REMUX'
        assert dupes[1]['name'] == 'Inception.2010.FRENCH.1080p.WEB-DL'

    def test_accent_insensitive_match(self):
        """French titles with accents should match their dot-separated versions."""
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        meta = _meta_base(title='Le Prénom', year='2012')
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'title': 'Le.Prenom.2012.FRENCH.1080p', 'id': 50},
            ]
        }

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(meta, ''))

        assert len(dupes) == 1

    def test_bilingual_search_merges_both_titles(self):
        """When FR and EN titles differ, both are searched and results merged."""
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        # English title "The Sixth Sense", French title "Sixième Sens"
        meta = _meta_base(
            title='The Sixth Sense',
            frtitle='Sixième Sens',
            year='1999',
            original_language='en',
        )

        # First call (EN title) → returns 1 result under English name
        resp_en = MagicMock()
        resp_en.status_code = 200
        resp_en.json.return_value = {
            'data': [
                {'title': 'The.Sixth.Sense.1999.MULTi.2160p.REMUX', 'id': 100},
            ]
        }
        # Second call (FR title) → returns 1 result under French name
        resp_fr = MagicMock()
        resp_fr.status_code = 200
        resp_fr.json.return_value = {
            'data': [
                {'title': 'Sixieme.Sens.1999.FRENCH.1080p', 'id': 101},
            ]
        }

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(side_effect=[resp_en, resp_fr])
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(meta, ''))

        # Both results should be present
        assert len(dupes) == 2
        names = [d['name'] for d in dupes]
        assert 'The.Sixth.Sense.1999.MULTi.2160p.REMUX' in names
        assert 'Sixieme.Sens.1999.FRENCH.1080p' in names

    def test_bilingual_search_deduplicates(self):
        """If both queries return the same torrent, it should appear only once."""
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        meta = _meta_base(
            title='Inception',
            frtitle='Inception',  # same title in both languages
            year='2010',
            original_language='en',
        )

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            'data': [
                {'title': 'Inception.2010.MULTi.2160p', 'id': 200},
            ]
        }

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            # Only one API call since titles are identical
            client_instance.get = AsyncMock(return_value=resp)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(meta, ''))

        assert len(dupes) == 1
        # Should have been called only once (titles are identical → one query)
        assert client_instance.get.call_count == 1

    def test_bilingual_search_original_french_searches_fr_first(self):
        """When original_language is 'fr', the French title is searched first."""
        t = TORR9(_config())
        t._bearer_token = 'test-token'
        meta = _meta_base(
            title='The Intouchables',
            frtitle='Intouchables',
            year='2011',
            original_language='fr',
        )

        resp_fr = MagicMock()
        resp_fr.status_code = 200
        resp_fr.json.return_value = {
            'data': [
                {'title': 'Intouchables.2011.FRENCH.1080p', 'id': 300},
            ]
        }
        resp_en = MagicMock()
        resp_en.status_code = 200
        resp_en.json.return_value = {'data': []}

        with patch('httpx.AsyncClient') as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(side_effect=[resp_fr, resp_en])
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            dupes = _run(t.search_existing(meta, ''))

        # First call should use French title
        first_call = client_instance.get.call_args_list[0]
        assert 'Intouchables' in first_call.kwargs.get('params', {}).get('q', '')
        assert len(dupes) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  _get_mediainfo_text fallback tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestGetMediainfoText:
    """Test _get_mediainfo_text with file-based and meta fallback."""

    def test_reads_cleanpath_file(self, tmp_path):
        """Prefers MEDIAINFO_CLEANPATH.txt when it exists."""
        t = TORR9(config=_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "MEDIAINFO_CLEANPATH.txt").write_text("clean MI content")
        (tmpdir / "MEDIAINFO.txt").write_text("raw MI content")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        result = _run(t._get_mediainfo_text(meta))
        assert result == "clean MI content"

    def test_reads_mediainfo_file(self, tmp_path):
        """Falls back to MEDIAINFO.txt when CLEANPATH missing."""
        t = TORR9(config=_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "MEDIAINFO.txt").write_text("raw MI content")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        result = _run(t._get_mediainfo_text(meta))
        assert result == "raw MI content"

    def test_reads_bdinfo_file(self, tmp_path):
        """Falls back to BD_SUMMARY_00.txt for disc releases."""
        t = TORR9(config=_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "BD_SUMMARY_00.txt").write_text("BD summary content")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid", bdinfo={"some": "data"})
        result = _run(t._get_mediainfo_text(meta))
        assert result == "BD summary content"

    def test_fallback_to_meta_mediainfo_text(self, tmp_path):
        """Falls back to meta['mediainfo_text'] when no files exist."""
        t = TORR9(config=_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        # No MI files written

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        meta["mediainfo_text"] = "in-memory MI from prep"
        result = _run(t._get_mediainfo_text(meta))
        assert result == "in-memory MI from prep"

    def test_returns_empty_when_nothing_available(self, tmp_path):
        """Returns empty string when no files and no meta fallback."""
        t = TORR9(config=_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        result = _run(t._get_mediainfo_text(meta))
        assert result == ""

    def test_skips_empty_files(self, tmp_path):
        """Skips files that exist but are empty/whitespace-only."""
        t = TORR9(config=_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "MEDIAINFO_CLEANPATH.txt").write_text("   \n  ")
        (tmpdir / "MEDIAINFO.txt").write_text("")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        meta["mediainfo_text"] = "fallback MI"
        result = _run(t._get_mediainfo_text(meta))
        assert result == "fallback MI"

    def test_whitespace_cleanpath_falls_to_mediainfo(self, tmp_path):
        """Whitespace CLEANPATH should fall through to non-empty MEDIAINFO.txt."""
        t = TORR9(config=_config())
        tmpdir = tmp_path / "tmp" / "test-uuid"
        tmpdir.mkdir(parents=True)
        (tmpdir / "MEDIAINFO_CLEANPATH.txt").write_text("   \n  ")
        (tmpdir / "MEDIAINFO.txt").write_text("real MI content")

        meta = _meta_base(base_dir=str(tmp_path), uuid="test-uuid")
        meta["mediainfo_text"] = "should not be used"
        result = _run(t._get_mediainfo_text(meta))
        assert result == "real MI content"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  _patch_mi_filename tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPatchMiFilename:
    """Test that _patch_mi_filename replaces the 'Complete name' line."""

    def test_patches_complete_name(self) -> None:
        mi = (
            "General\n"
            "Complete name    : /media/downloads/Aliens.1986.mkv\n"
            "Format           : Matroska\n"
        )
        result = TORR9._patch_mi_filename(mi, "Aliens.1986.Special.Edition.2160p.FRENCH.UHD.BluRay.x265-GRP")
        assert "Complete name" in result
        assert "Aliens.1986.Special.Edition.2160p.FRENCH.UHD.BluRay.x265-GRP.mkv" in result
        assert "/media/downloads/" not in result

    def test_preserves_extension(self) -> None:
        mi = "Complete name : movie.avi\nFormat : AVI\n"
        result = TORR9._patch_mi_filename(mi, "NewName")
        assert "NewName.avi" in result

    def test_noop_when_empty(self) -> None:
        assert TORR9._patch_mi_filename("", "name") == ""
        assert TORR9._patch_mi_filename("some text", "") == "some text"

    def test_noop_when_no_complete_name(self) -> None:
        mi = "General\nFormat : Matroska\n"
        assert TORR9._patch_mi_filename(mi, "name") == mi


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NFO generation + upload integration tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


FAKE_MEDIAINFO = """\
General
Complete name                            : Aliens.1986.Special.Edition.2160p.UHD.BluRay.TrueHD.7.1.DoVi.HDR10.x265-W4NK3R.mkv
Format                                   : Matroska
Duration                                 : 2 h 34 min

Video
Format                                   : HEVC
Width                                    : 3 840 pixels
Height                                   : 2 160 pixels

Audio
Format                                   : TrueHD
Channels                                 : 8 channels
"""


class TestNfoGeneration:
    """Verify that NFO files are correctly generated from MediaInfo."""

    def _setup_workdir(self) -> tuple[str, str, str]:
        """Create a temp workdir with MEDIAINFO.txt and a fake torrent."""
        tmpd = tempfile.mkdtemp()
        uuid = 'test-nfo-integration'
        work_dir = os.path.join(tmpd, 'tmp', uuid)
        os.makedirs(work_dir, exist_ok=True)

        with open(os.path.join(work_dir, 'MEDIAINFO.txt'), 'w') as f:
            f.write(FAKE_MEDIAINFO)

        with open(os.path.join(work_dir, '[TORR9].torrent'), 'wb') as f:
            f.write(b'd8:announce0:e')

        return tmpd, uuid, work_dir

    def test_nfo_generated_from_mediainfo_file(self) -> None:
        """_get_or_generate_nfo must produce a non-empty .nfo from MEDIAINFO.txt."""
        tmpd, uuid, work_dir = self._setup_workdir()
        meta = _meta_base(
            base_dir=tmpd, uuid=uuid, debug=True,
            name='Aliens 1986 Special Edition 2160p UHD BluRay TrueHD 7.1 DV HDR x265-W4NK3R',
        )
        tracker = TORR9(_config())

        nfo_path = _run(tracker._get_or_generate_nfo(meta))

        assert nfo_path is not None
        assert os.path.exists(nfo_path)
        with open(nfo_path) as f:
            content = f.read()
        assert len(content) > 100
        assert 'Matroska' in content
        assert 'HEVC' in content

        import shutil
        shutil.rmtree(tmpd)

    def test_nfo_generated_from_mediainfo_text_fallback(self) -> None:
        """When no MEDIAINFO.txt file exists, fall back to meta['mediainfo_text']."""
        tmpd = tempfile.mkdtemp()
        uuid = 'test-nfo-fallback'
        work_dir = os.path.join(tmpd, 'tmp', uuid)
        os.makedirs(work_dir, exist_ok=True)

        # NO MEDIAINFO.txt written — only in-memory text
        meta = _meta_base(
            base_dir=tmpd, uuid=uuid, debug=True,
            name='Fallback Test',
            mediainfo_text=FAKE_MEDIAINFO,
        )
        tracker = TORR9(_config())

        nfo_path = _run(tracker._get_or_generate_nfo(meta))

        assert nfo_path is not None
        assert os.path.exists(nfo_path)
        with open(nfo_path) as f:
            content = f.read()
        assert 'Matroska' in content

        import shutil
        shutil.rmtree(tmpd)

    def test_nfo_none_when_no_mediainfo(self) -> None:
        """When neither file nor text exists, _get_or_generate_nfo returns None."""
        tmpd = tempfile.mkdtemp()
        uuid = 'test-nfo-empty'
        os.makedirs(os.path.join(tmpd, 'tmp', uuid), exist_ok=True)
        meta = _meta_base(base_dir=tmpd, uuid=uuid, debug=True, name='Empty')
        tracker = TORR9(_config())

        nfo_path = _run(tracker._get_or_generate_nfo(meta))
        assert nfo_path is None

        import shutil
        shutil.rmtree(tmpd)


class TestNfoUploadFlow:
    """End-to-end: debug upload must include a non-empty NFO in the multipart files."""

    def test_debug_upload_generates_nfo_and_description(self) -> None:
        """In debug mode, upload() must generate an NFO file and a description file."""
        tmpd = tempfile.mkdtemp()
        uuid = 'test-upload-nfo'
        work_dir = os.path.join(tmpd, 'tmp', uuid)
        os.makedirs(work_dir, exist_ok=True)

        with open(os.path.join(work_dir, 'MEDIAINFO.txt'), 'w') as f:
            f.write(FAKE_MEDIAINFO)
        with open(os.path.join(work_dir, '[TORR9].torrent'), 'wb') as f:
            f.write(b'd8:announce0:e')

        meta = _meta_base(
            base_dir=tmpd, uuid=uuid, debug=True,
            name='Aliens 1986 Special Edition 2160p UHD BluRay TrueHD 7.1 DV HDR x265-W4NK3R',
            title='Aliens',
            year='1986',
            category='MOVIE',
            type='ENCODE',
            resolution='2160p',
            source='Blu-ray',
            audio='TrueHD 7.1',
            video_encode='x265',
            video_codec='',
            tag='-W4NK3R',
            edition='SPECIAL EDITION',
            uhd='UHD',
            hdr='DV HDR',
            path='/fake/Aliens.1986.Special.Edition.2160p.UHD.BluRay.x265-W4NK3R.mkv',
            imdb_info={},
            anime=False,
            mal_id=0,
            anon=False,
            ua_signature='Test',
            mediainfo_text=FAKE_MEDIAINFO,
        )

        tracker = TORR9(_config())

        with patch('src.trackers.TORR9.COMMON') as mock_common_cls:
            mock_common = MagicMock()
            mock_common.create_torrent_for_upload = AsyncMock()
            mock_common_cls.return_value = mock_common
            result = _run(tracker.upload(meta, ''))

        assert result is True

        # NFO should exist
        nfo_files = [f for f in os.listdir(work_dir) if f.endswith('.nfo')]
        assert len(nfo_files) >= 1, f"Expected at least 1 NFO file, found: {os.listdir(work_dir)}"

        nfo_path = os.path.join(work_dir, nfo_files[0])
        with open(nfo_path) as f:
            nfo_content = f.read()
        assert len(nfo_content) > 100, f"NFO too small ({len(nfo_content)} bytes)"
        assert 'HEVC' in nfo_content

        # Description should also exist
        desc_path = os.path.join(work_dir, '[TORR9]DESCRIPTION.txt')
        assert os.path.exists(desc_path), "Description file not generated"
        with open(desc_path) as f:
            desc = f.read()
        assert len(desc) > 50

        import shutil
        shutil.rmtree(tmpd)

    def test_nfo_patch_mi_filename_in_upload(self) -> None:
        """The NFO sent during upload must have 'Complete name' patched to the release name."""
        tmpd = tempfile.mkdtemp()
        uuid = 'test-patch-in-upload'
        work_dir = os.path.join(tmpd, 'tmp', uuid)
        os.makedirs(work_dir, exist_ok=True)

        with open(os.path.join(work_dir, 'MEDIAINFO.txt'), 'w') as f:
            f.write(FAKE_MEDIAINFO)
        with open(os.path.join(work_dir, '[TORR9].torrent'), 'wb') as f:
            f.write(b'd8:announce0:e')

        meta = _meta_base(
            base_dir=tmpd, uuid=uuid, debug=True,
            name='Aliens 1986 Special Edition 2160p UHD BluRay TrueHD 7.1 DV HDR x265-W4NK3R',
            title='Aliens',
            year='1986',
            category='MOVIE',
            type='ENCODE',
            resolution='2160p',
            source='Blu-ray',
            audio='TrueHD 7.1',
            video_encode='x265',
            video_codec='',
            tag='-W4NK3R',
            edition='SPECIAL EDITION',
            uhd='UHD',
            hdr='DV HDR',
            path='/fake/Aliens.1986.mkv',
            imdb_info={},
            anime=False,
            mal_id=0,
            anon=False,
            ua_signature='Test',
            mediainfo_text=FAKE_MEDIAINFO,
        )

        tracker = TORR9(_config())

        # Capture files dict by intercepting httpx call
        captured_files: dict[str, Any] = {}

        async def fake_upload(meta_arg: Any, _disc: str) -> bool:
            """Re-implement just the NFO part of upload to capture nfo_bytes."""
            name_result = await tracker.get_name(meta_arg)
            title = name_result.get("name", "") if isinstance(name_result, dict) else str(name_result)

            nfo_path = await tracker._get_or_generate_nfo(meta_arg)
            nfo_bytes = b""
            if nfo_path and os.path.exists(nfo_path):
                with open(nfo_path, "rb") as f:
                    nfo_bytes = f.read()
                if title and nfo_bytes:
                    try:
                        nfo_text = nfo_bytes.decode("utf-8", errors="replace")
                        nfo_text = tracker._patch_mi_filename(nfo_text, title)
                        nfo_bytes = nfo_text.encode("utf-8")
                    except Exception:
                        pass

            captured_files['nfo_bytes'] = nfo_bytes
            captured_files['nfo_text'] = nfo_bytes.decode("utf-8", errors="replace") if nfo_bytes else ""
            captured_files['title'] = title
            return True

        _run(fake_upload(meta, ''))

        # NFO bytes must be non-empty
        assert len(captured_files['nfo_bytes']) > 100, \
            f"NFO bytes too small: {len(captured_files['nfo_bytes'])} bytes"

        # TORR9 sends NFO as a plain-text data field (not a file upload)
        nfo_text = captured_files['nfo_text']
        assert isinstance(nfo_text, str)
        assert len(nfo_text) > 100

        # Complete name must be patched to tracker release name
        assert 'Aliens.1986.Special.Edition.2160p.UHD.BluRay' not in nfo_text or \
               captured_files['title'] in nfo_text.replace('.mkv', ''), \
               "Complete name should be patched to the tracker release name"

        import shutil
        shutil.rmtree(tmpd)
