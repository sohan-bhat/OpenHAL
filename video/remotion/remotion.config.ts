import {Config} from '@remotion/cli/config';

Config.setChromiumOpenGlRenderer('angle');
Config.setPublicDir('../assets');
Config.setVideoImageFormat('png');
Config.setCodec('h264');
Config.setCrf(16);
Config.setPixelFormat('yuv420p');
Config.setConcurrency(1);
