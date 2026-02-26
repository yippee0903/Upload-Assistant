# Tests for TORR9 tracker — torr9.xyz
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
        'announce_url': 'https://tracker.torr9.xyz/announce/FAKE_PASSKEY',
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
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Constructor ─────────────────────────────────────────────

class TestTorr9Init:
    def test_basic_init(self):
        t = TORR9(_config())
        assert t.tracker == 'TORR9'
        assert t.source_flag == 'TORR9'
        assert t.api_key == 'test-bearer-token-123'
        assert t.username == ''
        assert t.password == ''
        assert t.upload_url == 'https://api.torr9.xyz/api/v1/torrents/upload'
        assert t.torrent_url == 'https://torr9.xyz/torrents/'

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