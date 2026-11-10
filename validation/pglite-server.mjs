import { PGlite } from '@electric-sql/pglite';
import { PGLiteSocketServer,PGLiteSocketHandler } from '@electric-sql/pglite-socket';
const handle = PGLiteSocketHandler.prototype.handleData;
PGLiteSocketHandler.prototype.handleData = function(data) {
    this._chain = (this._chain || Promise.resolve()).then(async () => {
        this._buffer = Buffer.concat([this._buffer || Buffer.alloc(0),data]);
        this._frames ||= [];
        let sent=0;
        while(this._buffer.length >= 4) {
            const startup = !this._started;
            const header = startup ? 0 : 1;
            if(this._buffer.length < header+4) break;
            const size = this._buffer.readUInt32BE(header)+header;
            if(this._buffer.length < size) break;
            const frame=this._buffer.subarray(0,size);
            this._buffer=this._buffer.subarray(size);
            this._frames.push(frame);
            const type=startup?'startup':String.fromCharCode(frame[0]);
            this._started=true;
            if(['startup','p','Q','S','H','X'].includes(type)) {
                sent += await handle.call(this,Buffer.concat(this._frames));
                this._frames=[];
            }
        }
        return sent;
    });
    return this._chain;
};
const db = await PGlite.create(process.argv[3]);
const server = new PGLiteSocketServer({ db,port:Number(process.argv[2]),host:'127.0.0.1'});
await server.start();
console.log(await db.query('SELECT version()'));
process.on('SIGTERM',async()=>{ await server.stop(); await db.close(); process.exit(0); });
