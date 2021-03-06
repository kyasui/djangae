from mapreduce.mapper_pipeline import MapperPipeline
from mapreduce import parameters
from mapreduce import control
from mapreduce import context
from pipeline.util import for_name


BASE_PATH = '/_ah/mapreduce'
PIPELINE_BASE_PATH = BASE_PATH + '/pipeline'

class DjangaeMapperPipeline(MapperPipeline):

    def run(self, job_name, handler_spec, input_reader_spec, output_writer_spec=None, params=None, shards=None):
        """
            Overwriting this method allows us to pass the base_path properly, I know it's stupid but I think
            this is the cleanest way that still gives us a working Pipeline that we can chain
        """
        if shards is None:
          shards = parameters.config.SHARD_COUNT

        mapreduce_id = control.start_map(
            job_name,
            handler_spec,
            input_reader_spec,
            params or {},
            mapreduce_parameters={
                "done_callback": self.get_callback_url(),
                "done_callback_method": "GET",
                "pipeline_id": self.pipeline_id,
                "base_path": BASE_PATH,
            },
            shard_count=shards,
            output_writer_spec=output_writer_spec,
            queue_name=self.queue_name,
            )
        self.fill(self.outputs.job_id, mapreduce_id)
        self.set_status(console_url="%s/detail?mapreduce_id=%s" % (
            (parameters.config.BASE_PATH, mapreduce_id)))

    def callback(self, **kwargs):
        """
            Callback finish exists on the pipeline class, so we just use it as a nice
            wrapper for the static method attached to the MapReduceTask
        """
        ctx = context.get()
        params = ctx.mapreduce_spec.mapper.params
        finish_func = params.get('_finish', None)
        if not finish_func:
            return None
        finish_func = for_name(finish_func)
        return finish_func(**kwargs)


class MapReduceTask(object):
    """
        MapReduceTask base class, inherit this in a statically defined class and
        use .start() to run a mapreduce task

        You must define a staticmethod 'map' which takes in an arg of the entity being mapped over.
        Optionally define a staticmethod 'reduce' for the reduce stage (Not Implemented).

        You can pass any additional args and/or kwargs to .start(), which will then be passed into
        each call of .map() for you.

        Overwrite 'finish' with a static definition for a finish callback
    """
    shard_count = 3
    pipeline_class = MapperPipeline # Defaults to MapperPipeline which just runs map stage
    job_name = None
    queue_name = 'default'
    output_writer_spec = None
    mapreduce_parameters = {}
    countdown = None
    eta = None
    model = None
    map_args = []
    map_kwargs = {}


    def __init__(self, model=None):
        if model:
            self.model = model
        if not self.job_name:
            # No job name then we will just use the class
            self.job_name = self.get_class_path()

    def get_model_app_(self):
        app = self.model._meta.app_label
        name = self.model.__name__
        return '{app}.{name}'.format(
            app=app,
            name=name,
        )

    def get_class_path(self):
        return '{mod}.{cls}'.format(
            mod=self.__class__.__module__,
            cls=self.__class__.__name__,
        )

    @classmethod
    def get_relative_path(cls, func):
        return '{mod}.{cls}.{func}'.format(
            mod=cls.__module__,
            cls=cls.__name__,
            func=func.__name__,
        )

    @staticmethod
    def map(entity, *args, **kwargs):
        """
            Override this definition with a staticmethod map definition
        """
        raise NotImplementedError('You must supply a map function')

    @staticmethod
    def finish(**kwargs):
        """
            Override this with a static method for the finish callback
        """
        raise NotImplementedError('You must supply a finish function')

    def start(self, *args, **kwargs):
        mapper_parameters = {
            'model': self.get_model_app_(),
            'kwargs': kwargs,
            'args': args,
        }
        if 'map' not in self.__class__.__dict__:
            raise Exception('No static map method defined on class {cls}'.format(self.__class__))
        mapper_parameters['_map'] = self.get_relative_path(self.map)
        if 'finish' in self.__class__.__dict__:
            mapper_parameters['_finish'] = self.get_relative_path(self.finish)


        pipe = DjangaeMapperPipeline(
            self.job_name,
            'djangae.contrib.mappers.thunks.thunk_map',
            'djangae.contrib.mappers.readers.DjangoInputReader',
            params=mapper_parameters,
            shards=self.shard_count
        )
        pipe.start(base_path=PIPELINE_BASE_PATH)
