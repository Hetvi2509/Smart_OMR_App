import { Platform } from 'react-native';
import * as Sharing from 'expo-sharing';

import { reportDownload } from '../api/endpoints';

/**
 * Download a report PDF and hand it to the user.
 *
 * Shared by the Result and Reports screens so the auth header, the cache path
 * and the overwrite flag are decided in one place.
 *
 * Returns true when the file was handed off (share sheet on native, download
 * on web), false when it was saved but no share mechanism was available.
 */
export async function openReportPdf(reportId: number): Promise<boolean> {
  const { url, headers } = reportDownload(reportId);

  if (Platform.OS === 'web') {
    return downloadInBrowser(url, headers, reportId);
  }

  // Imported lazily: expo-file-system's File/Paths API is native-only. Its
  // web stub has no validatePath, so merely constructing a File in a browser
  // throws "this.validatePath is not a function" -- even inside a branch that
  // never runs there, if the import is evaluated at module load.
  const { File, Paths } = await import('expo-file-system');
  const target = new File(Paths.cache, `omr-report-${reportId}.pdf`);

  // idempotent: regenerating a report reuses the same filename, and without
  // this the second download of a report throws "file already exists".
  const file = await File.downloadFileAsync(url, target, {
    headers,
    idempotent: true,
  });

  if (!(await Sharing.isAvailableAsync())) return false;
  await Sharing.shareAsync(file.uri, {
    mimeType: 'application/pdf',
    dialogTitle: 'Result report',
    UTI: 'com.adobe.pdf',
  });
  return true;
}

/**
 * Save the PDF through the browser.
 *
 * The request needs an Authorization header, so the file cannot simply be
 * linked to: it is fetched, turned into an object URL, and handed to a
 * synthetic <a download> click.
 */
async function downloadInBrowser(
  url: string,
  headers: Record<string, string>,
  reportId: number,
): Promise<boolean> {
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Could not download the report (HTTP ${response.status}).`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = `omr-report-${reportId}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked on the next tick: revoking immediately can cancel the download
  // in some browsers before it has read the blob.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
  return true;
}
