import requests
import time
import sys


def run_e2e_test() -> int:
    fpath = 'sample_whatsapp_export.txt'

    print('Posting sample file...')
    try:
        with open(fpath, 'rb') as f:
            r = requests.post('http://127.0.0.1:8000/api/analyze/upload', files={'file':('sample.txt', f, 'text/plain')})

        print('Upload response:', r.status_code, r.text)
        if r.status_code == 200:
            cid = r.json().get('chat_id')
            time.sleep(1)
            rr = requests.get(f'http://127.0.0.1:8000/api/analyze/report/{cid}')
            print('Report fetch:', rr.status_code)
            print(rr.json())
            return 0
        else:
            print('Upload failed, not fetching report')
            return 1
    except Exception as e:
        print('Error during upload:', e)
        return 1


if __name__ == '__main__':
    sys.exit(run_e2e_test())
