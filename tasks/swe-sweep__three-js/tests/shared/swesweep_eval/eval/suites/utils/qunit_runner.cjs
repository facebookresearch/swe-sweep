#!/usr/bin/env node

const fs = require( 'node:fs' );
const path = require( 'node:path' );
const { pathToFileURL } = require( 'node:url' );
const { createRequire } = require( 'node:module' );

const [ repo, reportPath, ...files ] = process.argv.slice( 2 );
const requireFromRepo = createRequire( path.join( repo, 'package.json' ) );
const QUnit = requireFromRepo( 'qunit' );

globalThis.QUnit = QUnit;
QUnit.config.autostart = false;
QUnit.config.filter = '!-webonly';

const outcomes = {};
QUnit.on( 'testEnd', ( result ) => {

	const name = result.fullName.join( ' ' );
	outcomes[ name ] = result.status === 'passed' ? 'passed' :
		result.status === 'skipped' || result.status === 'todo' ? 'skipped' : 'failed';

} );

const finished = new Promise( ( resolve ) => {

	QUnit.on( 'runEnd', ( result ) => {

		fs.writeFileSync( reportPath, JSON.stringify( {
			outcomes,
			collection_error: false,
		} ) );
		process.exitCode = result.testCounts.failed > 0 ? 1 : 0;
		resolve();

	} );

} );

( async () => {

	try {

		for ( const prelude of [
			'test/unit/utils/console-wrapper.js',
			'test/unit/utils/qunit-utils.js',
		] ) {

			const absolute = path.join( repo, prelude );
			if ( fs.existsSync( absolute ) ) await import( pathToFileURL( absolute ).href );

		}

		for ( const file of files ) {

			await import( pathToFileURL( path.join( repo, file ) ).href );

		}

		QUnit.start();
		await finished;

	} catch ( error ) {

		fs.writeFileSync( reportPath, JSON.stringify( {
			outcomes,
			collection_error: true,
			error: String( error && error.stack || error ),
		} ) );
		process.exitCode = 1;

	}

} )();
