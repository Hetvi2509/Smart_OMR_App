import { useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { sheetImageSource } from '../api/endpoints';

export type SheetVariant = 'original' | 'annotated';

/**
 * A displayable source for a submission's sheet image.
 *
 * `variant` picks between the photo as uploaded and the engine's review
 * overlay, which rings every bubble the algorithm detected.
 *
 * The route is authenticated, so the image is fetched explicitly with the
 * bearer header rather than handed to <Image source={{uri, headers}}> to let
 * React Native's native image loader attach it -- that silently does not
 * work on this SDK, with no error surfaced anywhere.
 *
 * On native, the fetched bytes are NOT turned into a Blob: Expo's `fetch`
 * polyfill builds one as `new Blob([arrayBuffer])`
 * (expo/src/winter/fetch/FetchResponse.ts), and React Native's own Blob
 * class documents that it "currently only support[s] creating Blobs from
 * other Blobs" -- an ArrayBuffer is not one, so the resulting Blob is
 * silently empty. <Image> then has nothing to decode and the screen shows
 * the "not stored" placeholder for an image that is, in fact, stored. The
 * bytes are instead written straight to a temp file via expo-file-system,
 * and <Image> is given that file's own uri -- no Blob anywhere in the path.
 */
export function useSheetImage(submissionId: number, variant: SheetVariant = 'original') {
    const [uri, setUri] = useState<string | null>(null);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        const { uri: url, headers } = sheetImageSource(submissionId, variant);
        setFailed(false);
        setUri(null);

        let objectUrl: string | null = null;
        let cancelled = false;

        (async () => {
            try {
                const res = await fetch(url, { headers });
                if (!res.ok) throw new Error(String(res.status));

                if (Platform.OS === 'web') {
                    const blob = await res.blob();
                    if (cancelled) return;
                    objectUrl = URL.createObjectURL(blob);
                    setUri(objectUrl);
                    return;
                }

                // bytes()/arrayBuffer() are unaffected by the Blob gap above;
                // Expo's fetch builds those straight from the native response.
                const bytes = await res.bytes();
                if (cancelled) return;

                const { File, Paths } = await import('expo-file-system');
                const ext = variant === 'annotated' ? 'annotated' : 'sheet';
                const file = new File(Paths.cache, `sub_${submissionId}_${ext}.jpg`);
                // write() creates the file itself if it is not already there;
                // deleting first only matters for a stale copy from an
                // earlier, possibly-corrected result (e.g. after an override
                // changes the overlay for the same submission id).
                if (file.exists) file.delete();
                file.write(bytes);
                if (!cancelled) setUri(file.uri);
            } catch (err) {
                if (!cancelled) {
                    setFailed(true);
                    if (__DEV__) {
                        console.warn('useSheetImage fetch failed:', (err as Error)?.message || err);
                    }
                }
            }
        })();

        return () => {
            cancelled = true;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [submissionId, variant]);

    return {
        source: uri ? { uri } : null,
        failed,
    };
}
